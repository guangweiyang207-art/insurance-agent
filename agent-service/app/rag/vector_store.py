from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pymilvus import DataType, MilvusClient, AnnSearchRequest, RRFRanker

from app.rag.models import KnowledgeChunk
from app.core.logging import get_logger
logger = get_logger(__name__)
#MilvusVectorStore 是 Milvus 向量库的仓储封装，负责子块向量的入库、删除、混合检索
# 检索结果
@dataclass
class RetrievedChunk:
    source_id: int # 召回文档编号
    clause_id: int # 召回条款id
    parent_id: str  # 用于回查完整父块。
    document_name: str  # 引用来源展示名称。
    section_path: list[str]  # 子块所在的 Markdown 章节路径。
    content: str  # 用于 Rerank 的子块正文。
    score: float  # 初始为混合检索分数，Rerank 后替换为重排分数。



class MilvusVectorStore:
    """管理 Milvus Collection，并保存可检索的子块向量。"""

    def __init__(
        self,
        *,
        uri: str,
        collection_name: str,
        dense_dim: int = 1024,
    ) -> None:
        self.client = MilvusClient(uri=uri)
        self.collection_name = collection_name
        self.dense_dim = dense_dim
        logger.info("vector store 初始化完成")

    def close(self):
        self.client.close()

    def store(
        self,
        document_name: str,
        chunks: list[KnowledgeChunk],
        vectors: dict[str, Any],
        product_ids: list[int],
    ) -> None:
        # 尝试初始化collection
        self._initialize_collection()
        # 批处理
        entities = [
            self._to_entity(
                document_name,
                chunk,
                dense_vector=vectors["dense"][index],
                # 稀疏向量保留二维 batch 结构，这是 pymilvus 要求的格式。
                sparse_vector=vectors["sparse"][index: index + 1],
                product_ids=product_ids,
            )
            for index, chunk in enumerate(chunks)
        ]
        self.client.insert(collection_name=self.collection_name, data=entities)

    def delete_by_clause_id(self, clause_id: int) -> None:
        if not self.client.has_collection(self.collection_name):
            return
        self.client.delete(
            collection_name=self.collection_name,
            filter=f"clause_id == {clause_id}",
        )

    def search(
        self,
        query_vector: dict[str, Any],
        candidate_k: int,
        top_k: int,
        *,
        filter_expression: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        # search 前必须 load collection，否则报 released 状态（load 幂等）
        self.client.load_collection(self.collection_name)
        # 1. 单独做 dense 检索，拿到 COSINE 语义相似度（用于阈值过滤，与 RRF 排名分区分开）
        dense_results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector["dense"]],
            anns_field="dense_vector",
            search_params={"metric_type": "COSINE"},
            limit=candidate_k,
            filter=filter_expression,
            output_fields=["id"],
        )
        dense_hits = dense_results[0] if dense_results else []
        dense_scores: dict[str, float] = {
            str(hit["id"]): float(hit["distance"]) for hit in dense_hits
        }

        # 2. 混合检索（dense + sparse，RRF 融合）：候选池 candidate_k，最终返回 top_k
        requests = [
            AnnSearchRequest(
                data=[query_vector["dense"]],
                anns_field="dense_vector",
                param={"metric_type": "COSINE"},
                limit=candidate_k,
                filter=filter_expression,
            ),
            AnnSearchRequest(
                data=[query_vector["sparse"]],
                anns_field="sparse_vector",
                param={"metric_type": "IP"},
                limit=candidate_k,
                filter=filter_expression,
            ),
        ]
        results = self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=requests,
            ranker=RRFRanker(),
            limit=top_k,
            output_fields=output_fields or [],
        )
        raw_hits = results[0] if results else []

        # 3. 组装结果，score 用 dense COSINE 相似度（供上层阈值过滤）
        chunks = []
        for hit in raw_hits:
            chunk = self._to_retrieved_chunk(hit)
            chunk.score = dense_scores.get(str(hit["id"]), chunk.score)
            chunks.append(chunk)
        return chunks

    def _drop_collection(self):
        self.client.drop_collection(self.collection_name)

    def _initialize_collection(self) -> None:
        # 判断collection是否存在，不存在才创建
        if self.client.has_collection(self.collection_name):
            return
        # schema约束，也就是向量库的字段
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("clause_id", DataType.INT64)
        schema.add_field("product_ids", DataType.ARRAY, element_type=DataType.INT64, max_capacity=64)
        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=64)
        schema.add_field("document_name", DataType.VARCHAR, max_length=512)
        schema.add_field("section_path", DataType.VARCHAR, max_length=1024)
        schema.add_field("content", DataType.VARCHAR, max_length=8192)

        # 稠密、稀疏检索字段
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self.dense_dim)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)

        # 索引
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
        )

        # 创建collection
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )

    def _to_entity(
        self,
        document_name: str,
        chunk: KnowledgeChunk,
        *,
        dense_vector: Any,
        sparse_vector: Any,
        product_ids: list[int],
    ) -> dict[str, Any]:
        if chunk.parent_id is None:
            raise ValueError("only child chunks can be stored in Milvus")
        return {
            "id": str(chunk.id),
            "parent_id": str(chunk.parent_id),
            "document_name": document_name,
            "clause_id": chunk.clause_id,
            "product_ids": product_ids,
            "section_path": json.dumps(chunk.section_path, ensure_ascii=False),
            "content": chunk.content,
            "dense_vector": dense_vector,
            "sparse_vector": sparse_vector,
        }

    def _to_retrieved_chunk(self, hit: Any) -> RetrievedChunk:
        fields = hit.get("entity", hit)
        score = float(hit.get("distance", hit.get("score", 0.0)))
        return RetrievedChunk(
            source_id=0,
            clause_id=fields["clause_id"],
            parent_id=str(fields["parent_id"]),
            document_name=str(fields["document_name"]),
            section_path=self._section_path(fields.get("section_path")),
            content=str(fields["content"]),
            score=score,
        )

    def _section_path(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(item) for item in json.loads(str(value))]