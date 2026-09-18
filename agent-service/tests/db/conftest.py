from app.core.logging import configure_logging
configure_logging(level="DEBUG")
import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)  # 手动控制sqlalchemy的日志级别
from typing import AsyncGenerator
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
from app.core.config import settings


# ──────────── Step 1.测试用实体 ────────────
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "test_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column(unique=True)

    def __repr__(self):
        return f"User(id={self.id}, name={self.name}, email={self.email})"

# ──────────── Step 2.连接池 ────────────

# 1. 创建内存数据库引擎（所有测试函数共享）
_engine = create_async_engine(
    settings.database_url,
    echo=False,  # 是否打印SQL语句,开发调试时打开
    pool_size=10,  # 连接池的活跃连接数
    max_overflow=20,  # 连接池最大连接数
    pool_recycle=3600,  # 回收空闲连接的等待时间
    pool_pre_ping=True,  # 拿连接前检查是否还活着
)

# 2. 创建Session工厂, expire_on_commit是指commit后不标记对象为过期，避免多次查询
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

# ──────────── Step 3.夹具 ────────────

# 1.初始化测试用数据库表、销毁测试用数据库表（自动执行）
@pytest_asyncio.fixture(autouse=True)
async def setup_teardown():
    """每个测试用例：自动创建表 → 执行测试 → 自动清理表"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

# 2.为每个测试函数提供独立的Session(按需引用)
@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """提供一个独立的会话供测试使用"""
    s = _session_factory()
    try:
        yield s
    finally:
        await s.close()



# 5.预先插入测试数据(按需引用)
@pytest_asyncio.fixture
async def init_test_data(session):
    """预先插入一些基础数据供测试使用"""
    async with session.begin():
        test_users = [
            User(name="Alice", email="alice@itheima.com"),
            User(name="Bob", email="bob@itheima.com"),
            User(name="Charlie", email="charlie@itheima.com"),
        ]
        session.add_all(test_users)