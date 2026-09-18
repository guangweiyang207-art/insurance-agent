"""保险知识库构建与检索模块。"""
from .models import KnowledgeDocument
from .pipeline import KnowledgeBuildPipeline
from .retrieval import KnowledgeRetriever
from .vector_store import MilvusVectorStore, RetrievedChunk
from .crud import PostgresKnowledgeRepository
from ..core.database import get_session_factory
from ..core.config import settings
from ..core.logging import get_logger
from .embedding import BGEM3Embedding

logger = get_logger(__name__)

_vector_store: MilvusVectorStore = None
_retriever: KnowledgeRetriever = None
_pipeline: KnowledgeBuildPipeline = None

async def init_rag_module():
    global _vector_store
    global _retriever
    global _pipeline

    # 未配置 MILVUS_URI 时跳过知识库模块（本地无 Milvus 时服务仍可启动，条款检索降级不可用）
    if not settings.milvus_uri:
        logger.warning("MILVUS_URI 未配置，跳过知识库(RAG)模块初始化，条款检索功能不可用")
        return

    # 向量模型
    _embedding = BGEM3Embedding()

    # 向量库
    _vector_store = MilvusVectorStore(
        uri=settings.milvus_uri,
        collection_name=settings.milvus_collection,
    )
    # 数据库
    _knowledge_repository = PostgresKnowledgeRepository(get_session_factory())

    # Retriever
    _retriever = KnowledgeRetriever(
        rerank_model=settings.rerank_model,
        embedding=_embedding,
        vector_store=_vector_store,
        repository=_knowledge_repository
    )

    # pipeline
    _pipeline = KnowledgeBuildPipeline(
        _knowledge_repository,
        _vector_store,
        _embedding
    )

def retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        raise RuntimeError("知识库(RAG)模块未初始化：未配置 MILVUS_URI，条款检索不可用")
    return _retriever

def pipeline() -> KnowledgeBuildPipeline:
    global _pipeline
    return _pipeline

async def dispose_rag():
    global _vector_store
    if _vector_store is not None:
        _vector_store.close()


__all__ = [
    'init_rag_module',
    'dispose_rag',
    'pipeline',
    'retriever',
    'KnowledgeRetriever',
    'RetrievedChunk',
    'KnowledgeBuildPipeline',
    'KnowledgeDocument',
]