from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)

if not settings.database_url:
    raise RuntimeError("database_url未配置，初始化数据库失败！")

# 1. 内部持有的引擎和会话工厂（不对外暴露，保持内聚）
_engine: AsyncEngine = None
_async_session_factory = None

# 2. 统一管理：初始化数据库、自动建表
async def init_db():
    global _engine
    global _async_session_factory
    _engine = create_async_engine(settings.database_url, echo=False, pool_size=10, max_overflow=20)
    _async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    # 自动建表：导入表模型以注册到 SQLAlchemy metadata
    from .base import Base
    from ..chat_thread.models import ChatThreadTable  # noqa: F401
    from ..rag.models import DocumentTable, ParentChunkTable, ChildChunkTable  # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库初始化成功")


# 3.定义一个函数，用来获取session_factory
def get_session_factory():
    return _async_session_factory

# 3. 依赖注入函数：获取数据库异步会话（供路由使用）
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


# 4. 统一管理：关闭数据库（销毁连接池）
async def close_db():
    await _engine.dispose()
    logger.info("数据库连接已关闭")