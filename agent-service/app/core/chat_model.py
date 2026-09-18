from typing import Any

from langchain.chat_models import init_chat_model

from .config import APP_ROOT, settings


def create_chat_model(*, model: str | None = None, **kwargs: Any):
    """将服务配置显式传给 LangChain；读取 .env 不会自动设置进程环境变量。"""
    if not settings.deepseek_api_key or not settings.deepseek_api_key.strip():
        raise RuntimeError(
            f"DEEPSEEK_API_KEY 未配置，请在 {APP_ROOT / '.env'} 中填写。"
        )
    return init_chat_model(
        model or settings.chat_model,
        model_provider="deepseek",
        api_key=settings.deepseek_api_key,
        api_base=settings.deepseek_base_url,
        **kwargs,
    )
