from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "healthy",
        "service": "biz-service",
        "port": settings.server_port,
        "time": datetime.now(timezone.utc).isoformat(),
    }
