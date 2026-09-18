"""
通过业务服务拉取所有产品及主条款，去重后批量构建 RAG 知识库。

用法:
    uv run python scripts/ingest_rag_document.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# hm-insurance 项目根目录：条款的 file_path 以它为基准（相对路径）
HM_ROOT = Path(__file__).resolve().parents[2]

from pymilvus import exceptions as milvus_exc

from app.clients.biz_client import biz_client
from app.core.config import settings
from app.core.database import init_db, get_session_factory, close_db
from app.core.logging import get_logger
from app.rag.crud import PostgresKnowledgeRepository
from app.rag.embedding import BGEM3Embedding
from app.rag.models import KnowledgeDocument
from app.rag.pipeline import KnowledgeBuildPipeline
from app.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


async def fetch_all_products() -> list[dict]:
    """翻页拉取全部产品。"""
    all_items: list[dict] = []
    page = 1
    page_size = 50
    while True:
        result = await biz_client.list_products(page=page, page_size=page_size)
        items = result.get("items", [])
        if not items:
            break
        all_items.extend(items)
        if len(items) < page_size:
            break
        page += 1
    logger.info("共拉取到 %d 个产品", len(all_items))
    return all_items


async def collect_unique_main_clauses(products: list[dict]) -> dict[int, dict]:
    """
    遍历产品查询主条款，按 clause_id 去重并记录关联的 product_ids。

    Returns:
        {clause_id: {"clause": {...}, "product_ids": [1, 2, ...]}}
    """
    seen: dict[int, dict] = {}

    for product in products:
        product_id = product["id"]
        result = await biz_client.list_clauses_of_product(product_id=product_id)
        clauses = result.get("data", [])

        for clause in clauses:
            if clause.get("clause_type") != "main_clause":
                continue
            clause_id = clause["id"]
            if clause_id in seen:
                seen[clause_id]["product_ids"].append(product_id)
            else:
                seen[clause_id] = {
                    "clause": clause,
                    "product_ids": [product_id],
                }

    logger.info("去重后共 %d 个主条款", len(seen))
    return seen


async def ingest_all() -> None:
    """主流程：清库 → 拉取 → 去重 → 逐文档入库。"""

    # 1. 初始化外部依赖
    logger.info("初始化数据库…")
    await init_db()

    logger.info("初始化业务服务客户端…")
    await biz_client.init()

    # 2. 清空向量库 collection，避免历史数据污染
    vector_store = MilvusVectorStore(
        uri=settings.milvus_uri,
        collection_name=settings.milvus_collection,
    )
    try:
        vector_store._drop_collection()
        logger.info("已清空向量库 collection: %s", settings.milvus_collection)
    except milvus_exc.MilvusException:
        logger.info("向量库 collection 不存在，无需清空")

    # 3. 拉取产品
    products = await fetch_all_products()
    if not products:
        logger.warning("未拉取到任何产品，退出")
        return

    # 4. 查询主条款并去重
    unique_clauses = await collect_unique_main_clauses(products)
    if not unique_clauses:
        logger.warning("未找到任何主条款，退出")
        return

    # 5. 构建 Pipeline
    session_factory = get_session_factory()
    repository = PostgresKnowledgeRepository(session_factory)
    embedding = BGEM3Embedding()

    pipeline = KnowledgeBuildPipeline(
        repository=repository,
        vector_store=vector_store,
        embedding=embedding,
    )

    # 6. 逐个文档送入 pipeline
    total = len(unique_clauses)
    success = 0
    for idx, (clause_id, info) in enumerate(unique_clauses.items(), 1):
        clause = info["clause"]
        product_ids = info["product_ids"]

        doc = KnowledgeDocument(
            clause_id=clause_id,
            document_name=clause["file_name"],
            source_uri=str(HM_ROOT / clause["file_path"]),
            product_ids=product_ids,
        )

        logger.info(
            "[%d/%d] 开始处理: %s (关联 %d 个产品)",
            idx, total, clause["file_name"], len(product_ids),
        )
        ok = await pipeline.ingest_document(doc)
        if ok:
            success += 1
        else:
            logger.error("[%d/%d] 处理失败: %s", idx, total, clause["file_name"])

    logger.info("全部完成: %d/%d 个文档入库成功", success, total)

    # 7. 清理资源
    vector_store.close()
    await biz_client.close()
    await close_db()


if __name__ == "__main__":
    asyncio.run(ingest_all())
