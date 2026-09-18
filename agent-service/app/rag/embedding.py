from __future__ import annotations

from typing import Any
from ..core.logging import get_logger

logger = get_logger(__name__)


class BGEM3Embedding:
    """加载一次 BGE-M3，同时生成稠密向量和稀疏向量。"""

    def __init__(self) -> None:
        from pymilvus.model.hybrid import BGEM3EmbeddingFunction
        from ..core.config import settings

        # 模型权重较大，因此保存在对象中，由整个应用复用。
        self.embedding_function = BGEM3EmbeddingFunction(model_name=settings.embedding_model)

        logger.info("BGEM3Embedding initialized")

    def dim(self) -> int:
        return self.embedding_function.dim['dense']

    def embed_query(self, text: str) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("query must not be empty")
        # embedding_function 默认只支持批处理，传递时要确保向量化的文本是一个列表
        # embedding_function 的返回值是一个dict，其中包含 dense / sparse
        result = self.embedding_function([text])
        return {'dense': result['dense'][0], 'sparse': result['sparse'][0:1]}

    def embed_documents(self, texts: list[str]) -> dict[str, Any]:
        if not texts:
            raise ValueError("texts must not be empty")
        return self.embedding_function(texts)