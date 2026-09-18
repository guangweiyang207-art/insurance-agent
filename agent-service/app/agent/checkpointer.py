from __future__ import annotations

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_checkpointer_pool: AsyncConnectionPool | None = None

if not settings.database_url:
    raise RuntimeError("database_url未配置，初始化checkpointer失败！")

def _build_psycopg_conn_string() -> str:
    """从现有配置拼接 psycopg 格式的连接字符串"""
    url = settings.database_url
    # SQLAlchemy 格式: postgresql+asyncpg://user:pass@host:5432/db
    # psycopg 格式:    postgresql://user:pass@host:5432/db
    return url.replace("+asyncpg", "")

async def init_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer_pool
    # 获取数据库连接地址
    conn_string = _build_psycopg_conn_string()
    # 初始化连接池
    _checkpointer_pool = AsyncConnectionPool(
        conninfo=conn_string, # postgresql://user:pass@host:5432/db
        min_size=2,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await _checkpointer_pool.open()
    # 初始化Checkpointer
    checkpointer = AsyncPostgresSaver(_checkpointer_pool)
    # 自动建表
    await checkpointer.setup()
    logger.info("checkpointer 初始化完成")
    return checkpointer


async def close_checkpointer():
    global _checkpointer_pool
    if _checkpointer_pool is not None:
        await _checkpointer_pool.close()
        _checkpointer_pool = None
        logger.info("checkpointer 连接池已关闭")