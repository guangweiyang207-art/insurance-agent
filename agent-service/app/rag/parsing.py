from __future__ import annotations

from typing import Any

from mineru import MinerU
from ..core.logging import get_logger
logger = get_logger(__name__)

class MinerUParser:
    """调用 MinerU API，将 PDF 等原始文档解析为 Markdown。"""

    def __init__(
        self,
        *,
        token: str | None,
        base_url: str | None = None,
        flash_base_url: str | None = None,
    ) -> None:
        # 只传递实际配置的地址，未配置时使用 MinerU SDK 默认服务地址。
        options = {}
        if base_url:
            options["base_url"] = base_url
        if flash_base_url:
            options["flash_base_url"] = flash_base_url
        self.client = MinerU(token, **options)
        logger.info("mineru parser 初始化完成")

    def parse(
        self,
        source_uri: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        """解析单个文档，Pipeline 后续只依赖 Markdown，不依赖 MinerU 实体。"""

        result = self.client.extract(source_uri, **(options or {}))
        # MinerU 请求可能正常返回但任务处理失败，因此必须检查任务状态。
        if result.state != "done" or result.markdown is None:
            raise RuntimeError(result.error or f"MinerU parse failed: {result.state}")
        return result.markdown
