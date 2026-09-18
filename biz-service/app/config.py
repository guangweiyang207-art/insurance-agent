from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    server_port: int = 8001
    business_database_url: str = "postgresql://insurance:insurance123@192.168.150.101:5432/insurance_biz"
    jwt_issuer: str = "hm-insurance"
    jwt_secret: str = "change-me-in-dev"
    jwt_access_token_minutes: int = 15
    jwt_refresh_token_days: int = 7
    refresh_token_cookie_name: str = "hm_refresh_token"
    refresh_token_cookie_secure: bool = False
    refresh_token_cookie_samesite: str = "lax"
    app_workspace_root: Path = PROJECT_ROOT


@lru_cache
def get_settings() -> Settings:
    return Settings()
