from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, replace

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.rag.embedding import BGEM3Embedding
from app.rag.crud import PostgresKnowledgeRepository
from app.rag.vector_store import RetrievedChunk, MilvusVectorStore
from app.core.logging import get_logger
logger = get_logger(__name__)

_redis = None  # redis.asyncio 客户端，懒加载


def _get_redis():
    """懒加载 Redis 客户端；未配置 REDIS_URL 或未装 redis 包时返回 None（跳过缓存）。"""
    global _redis
    if not settings.redis_url:
        return None
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            # protocol=2 兼容 Redis 5.x（redis-py 8 默认 RESP3 会发 HELLO，老版 Redis 不支持）
            _redis = aioredis.from_url(settings.redis_url, decode_responses=True, protocol=2)
        except ImportError:
            logger.warning("redis_package_not_installed")
            return None
    return _redis


def _cache_key(product_id: int, query: str) -> str:
    digest = hashlib.md5(query.encode("utf-8")).hexdigest()
    return f"rag:{product_id}:{digest}"


def _serialize(chunks: list[RetrievedChunk]) -> str:
    return json.dumps([asdict(c) for c in chunks], ensure_ascii=False)


def _deserialize(data: str) -> list[RetrievedChunk]:
    return [RetrievedChunk(**item) for item in json.loads(data)]


class KnowledgeRetriever:
    """编排召回、重排和父块回查。"""

    output_fields = [
        "clause_id",
        "parent_id",
        "document_name",
        "section_path",
        "content",
    ]

    def __init__(
        self,
        rerank_model: str,
        *,
        embedding: BGEM3Embedding,
        vector_store: MilvusVectorStore,
        repository: PostgresKnowledgeRepository,
    ) -> None:
        # 如果开启rerank功能，再导入rerank组件
        if settings.rerank_enable:
            from FlagEmbedding import FlagReranker
            self.reranker = FlagReranker(rerank_model)

        self.embedding = embedding
        self.vector_store = vector_store
        self.repository = repository
        self._query_rewriter = None  # 懒加载，仅开启查询改写时使用
        logger.info("knowledge retrieval 初始化完成")

    async def search(self, query:str, product_id: int, top_k:int) -> list[RetrievedChunk]:
        # 0.查询改写（可选）：把口语问法转成条款术语，提升召回
        query = await self._rewrite_query(query)
        # 0.5 缓存读：命中直接返回，跳过向量化与检索
        redis = _get_redis()
        if redis is not None:
            try:
                cached = await redis.get(_cache_key(product_id, query))
                if cached:
                    logger.info("rag_cache_hit", product_id=product_id)
                    return _deserialize(cached)
            except Exception as exc:
                logger.warning("rag_cache_read_failed", error=type(exc).__name__)
        # 1.问题向量化（BGE-M3 CPU 推理，放线程池避免阻塞事件循环）
        vectors = await asyncio.to_thread(self.embedding.embed_query, query)
        # 2.检索Milvus（同步 HTTP 调用，放线程池）
        chunks = await asyncio.to_thread(
            self.vector_store.search,
            vectors,
            candidate_k=settings.rag_candidate_k,
            top_k=top_k,
            filter_expression=_build_filter(product_id), # ARRAYS_CONTAINS(product_ids, 1)
            output_fields=self.output_fields,
        )
        # 2.5 相似度阈值过滤：reranker 关闭时，用 dense COSINE 相似度过滤低相关块，避免答非所问
        if not settings.rerank_enable:
            chunks = [c for c in chunks if c.score >= settings.rag_similarity_threshold]
        # 3.重排
        reranked:list[RetrievedChunk] = self.rerank(query, chunks)[: top_k]

        # 4.同一父块命中多个子块时，只返回一次完整父块，减少重复上下文。
        parent_counts: dict[str, int] = {}
        # 统计子块的parent_id出现次数
        for chunk in reranked:
            parent_counts[chunk.parent_id] = (
                parent_counts.get(chunk.parent_id, 0) + 1
            )
        # 找出parent_id > 1的块
        repeated_parent_ids = [
            parent_id
            for parent_id, count in parent_counts.items()
            if count > 1
        ]
        # 查询父块
        parents = await self.repository.get_parent_chunks(repeated_parent_ids)

        # 5.封装为最终结果返回（查询出父块的子块移除，用父块作为结果）
        evidence: list[RetrievedChunk] = []
        added_parent_ids: set[str] = set() # 记录已添加的parent_id
        for chunk in reranked:
            # 如果parent已经记录过，跳过
            if chunk.parent_id in added_parent_ids:
                continue
            added_parent_ids.add(chunk.parent_id)
            # 编号递增

            chunk.source_id = f"ref-{(len(evidence) + 1):03d}"
            # 尝试获取查询到的父块
            parent = parents.get(chunk.parent_id, None)
            if parent is None:
                # 如果没有，说明是无重复的子块，则直接添加到最终结果
                evidence.append(chunk)
            else:
                # 如果有，说明是重复子块，用父块内容代替
                chunk.content = parent.content
                evidence.append(chunk)
        # 5.5 缓存写：结果写入 Redis（TTL 过期自动失效）
        if redis is not None:
            try:
                await redis.set(_cache_key(product_id, query), _serialize(evidence), ex=settings.rag_cache_ttl)
            except Exception as exc:
                logger.warning("rag_cache_write_failed", error=type(exc).__name__)
        return evidence

    async def _rewrite_query(self, query: str) -> str:
        """查询改写：把用户口语问法转成保险条款术语，提升检索召回率。

        默认关闭（增加一次 LLM 调用，会拖慢响应）；开启 RAG_QUERY_REWRITE_ENABLE 后生效。
        失败时静默回退到原始 query，不影响检索主流程。
        """
        if not settings.rag_query_rewrite_enable:
            return query
        if self._query_rewriter is None:
            from ..core.chat_model import create_chat_model
            self._query_rewriter = create_chat_model(extra_body={"thinking": {"type": "disabled"}})
        try:
            result = await self._query_rewriter.ainvoke([
                SystemMessage(
                    content="把用户的保险咨询问题改写成一段简短的检索查询，"
                            "用保险条款中的正式术语表达，去掉口语化和多余信息。"
                            "只输出改写后的查询文本，不要任何解释。"
                ),
                HumanMessage(content=query),
            ])
            rewritten = str(result.content).strip()
            if rewritten:
                logger.info("query_rewritten", original=query, rewritten=rewritten)
                return rewritten
        except Exception as exc:
            logger.error("query_rewrite_failed", error=type(exc).__name__)
        return query

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        if not settings.rerank_enable or self.reranker is None:
            # 关闭Reranker
            return chunks
        # 重排打分
        scores = self.reranker.compute_score([[query, chunk.content] for chunk in chunks])
        if not isinstance(scores, list):
            scores = [float(scores)]
        # 用新得分替换旧得分
        reranked = [
            replace(chunk, score=float(score))
            for chunk, score in zip(chunks, scores, strict=True)
        ]
        # 排序
        return sorted(reranked, key=lambda chunk: chunk.score, reverse=True)

def _build_filter(product_id: int | None) -> str | None:
    if product_id is None:
        return None
    return f"ARRAY_CONTAINS(product_ids, {product_id})"