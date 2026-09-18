import time
from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid

from starlette.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.logging import configure_logging, get_logger
from .core.database import init_db, close_db
from .agent.checkpointer import init_checkpointer, close_checkpointer
from .agent.graph import create_agent
from .clients.biz_client import biz_client
from .rag import init_rag_module, dispose_rag

# 初始化日志配置
configure_logging(level=settings.log_level, log_format=settings.log_format)

logger = get_logger(__name__)


def _setup_langsmith() -> None:
    """按配置启用 LangSmith 追踪（可选，配置 key 后自动追踪 LLM/工具调用）。"""
    if settings.langsmith_tracing and settings.langsmith_api_key:
        import os
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info("langsmith_tracing_enabled", project=settings.langsmith_project)


# 生命周期管理（预留）
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("agent_service_starting", app_version=settings.app_version)
        _setup_langsmith()
        # 初始化数据库
        await init_db()
        # 初始化biz-service的客户端
        await biz_client.init()
        # 初始化
        await init_rag_module()
        # 初始化Checkpointer
        checkpointer = await init_checkpointer()
        # 初始化agent, 必须注册为全局唯一的agent，把它注册app.state中
        app.state.agent = await create_agent(checkpointer)
        yield
    finally:
        logger.info("agent_service_stopping")
        # 关闭数据库
        await close_db()
        # 关闭
        await dispose_rag()
        # 关闭Checkpointer
        await close_checkpointer()
        # 关闭biz-service客户端
        await biz_client.close()
        logger.info("agent_service_stopped")

# 初始化FastAPI
app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# 日志输出中间件
@app.middleware("http")
async def add_log_uuid(request: Request, call_next):
    # 1. 清理并生成新的请求上下文
    structlog.contextvars.clear_contextvars()
    request_id = str(uuid.uuid4())

    # 2. 绑定当前请求的核心信息
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    # 3. 记录请求结束日志
    logger.info("request_processed", status_code=response.status_code, duration=f"{duration_ms:.4f}ms")
    return response

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局兜底异常处理器：未捕获异常返回统一格式，避免裸 500 与堆栈泄露
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", method=request.method, path=request.url.path, error=type(exc).__name__)
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"})

from .chat_thread.router import router as chat_thread_router
from .agent.router import router as agent_router
# 挂载路由
app.include_router(chat_thread_router, prefix="/api/v1", tags=["会话管理相关接口"])
app.include_router(agent_router, prefix="/api/v1", tags=["Agent对话相关接口"])

@app.get("/")
async def healthy():
    return {"status": "running", "port": str(settings.app_port)}

if __name__ == "__main__":
    import uvicorn
    # 启动命令：python -m app.main
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=True
    )