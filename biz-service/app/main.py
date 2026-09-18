from datetime import datetime, timezone
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .responses import http_exception_handler
from .routers import auth, claims, clauses, health, orders, plans, policies, premium, products

logger = logging.getLogger("biz-service")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="hm-insurance biz-service")
    app.add_exception_handler(HTTPException, http_exception_handler)

    # 全局兜底异常处理器：未捕获异常返回统一格式，避免裸 500 与堆栈泄露
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(products.router, prefix="/api/v1/products")
    app.include_router(clauses.router, prefix="/api/v1/clauses")
    app.include_router(premium.router, prefix="/api/v1/premium")
    app.include_router(plans.router, prefix="/api/v1/insurance-plans")
    app.include_router(policies.router, prefix="/api/v1/policies")
    app.include_router(claims.router, prefix="/api/v1")
    app.include_router(orders.router, prefix="/api/v1/orders")
    app.state.started_at = datetime.now(timezone.utc)
    app.state.port = settings.server_port
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=get_settings().server_port,
        reload=True,
    )
