from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 以当前文件为基准，找向上2级的父目录，也就是项目的根目录
APP_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    # 设置.env文件的路径，默认是项目根目录下的.env
    model_config = SettingsConfigDict(
        env_file=(APP_ROOT / ".env",),
        env_file_encoding="utf-8",
        extra="ignore", # 本类中未定义而.env中出现的字段处理方案
    )
    # 应用信息
    app_name: str = "agent-service"
    app_version: str = "0.1.0"
    app_port: int = Field(default=8002, alias="APP_PORT")

    # 日志级别
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="console", alias="LOG_FORMAT")

    # 虚拟机地址
    infra_host: str | None = Field(default=None, alias="INFRA_HOST")

    # 业务端地址
    business_service_url: str | None = Field(default=None, alias="BUSINESS_SERVICE_URL")

    # 数据库配置
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str | None = Field(default=None, alias="POSTGRES_DB")
    postgres_user: str | None = Field(default=None, alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, alias="POSTGRES_PASSWORD")

    # 对话模型
    chat_model: str = Field(default="deepseek-flash", alias="CHAT_MODEL")

    # mineru
    mineru_token: str | None = Field(default=None, alias="MINERU_TOKEN")

    # auth
    jwt_secret: str | None = Field(default=None, alias="JWT_SECRET")
    jwt_issuer: str = Field(default="hm-insurance", alias="JWT_ISSUER")

    # LangSmith 可观测性（可选，配置 key 后自动追踪 LLM / 工具调用 / 链路耗时）
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="hm-insurance", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")

    # DeepSeek配置
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com",alias="DEEPSEEK_BASE_URL")

    # Reranker开关
    rerank_enable: bool = Field(default=False, alias="RERANK_ENABLE")

    # RAG相关参数
    milvus_uri: str | None = Field(default=None, alias="MILVUS_DB_PATH")
    milvus_collection: str = Field(
        default="insurance_knowledge_chunks",
        alias="MILVUS_COLLECTION",
    )
    markdown_optimizer_model: str = Field(default="deepseek-v4-pro",alias="MARKDOWN_OPTIMIZER_MODEL")
    rag_child_target_chars: int = Field(default=500, alias="RAG_CHILD_TARGET_CHARS")
    rag_child_overlap_chars: int = Field(default=80, alias="RAG_CHILD_OVERLAP_CHARS")
    rerank_model: str = Field(default="BAAI/bge-reranker-v2-m3",alias="RERANK_MODEL")
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    rag_candidate_k: int = Field(default=20, alias="RAG_CANDIDATE_K")
    rag_similarity_threshold: float = Field(default=0.4, alias="RAG_SIMILARITY_THRESHOLD")
    rag_query_rewrite_enable: bool = Field(default=False, alias="RAG_QUERY_REWRITE_ENABLE")

    # Redis 缓存（可选，RAG 检索结果缓存；未配置时自动跳过缓存）
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    rag_cache_ttl: int = Field(default=3600, alias="RAG_CACHE_TTL")



    @model_validator(mode="after")
    def derive_infra_urls(self) -> "Settings":
        # 拼接数据库地址
        if self.database_url is None and self.infra_host:
            if self.postgres_db and self.postgres_user and self.postgres_password:
                self.database_url = (
                    "postgresql+asyncpg://"
                    f"{self.postgres_user}:{self.postgres_password}"
                    f"@{self.infra_host}:{self.postgres_port}/{self.postgres_db}"
                )
        # 拼接业务端地址
        if self.business_service_url is None and self.infra_host:
            self.business_service_url = f"http://{self.infra_host}:8001"
        # Milvus 使用 HTTP URI；未单独配置时与其它基础设施共用主机。
        if self.milvus_uri is None and self.infra_host:
            self.milvus_uri = f"http://{self.infra_host}:19530"
        return self

settings = Settings()