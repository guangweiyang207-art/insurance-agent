from ..core.chat_model import create_chat_model
from ..core.logging import get_logger
logger = get_logger(__name__)

MARKDOWN_OPTIMIZATION_PROMPT = """
下面这份Markdown文档是从保险条款PDF解析得来，由于PDF中的各个小节是以表格形式存在，所以解析时出现错乱。你分析内容，帮我转为格式正确的Markdown，特别是标题编号要正确。
- 标题等级要从1级标题开始，逐层增加，目录和文档名不计入标题等级。
- 输出结果中不要包含正文开始之前的部分。
- 输出结果只包含Markdown正文，不要解释或代码围栏。
- 不要修改保险条款。
""".strip()


class MarkdownOptimizer:
    """使用 DeepSeek 修复 MinerU 解析后的 Markdown 结构。"""

    def __init__(
        self,
        *,
        model: str,
        **kwargs
    ) -> None:
        # 初始化模型
        self._client = create_chat_model(
            model=model,
            extra_body={'thinking': {'type': 'disabled'}},
            **kwargs
        )
        logger.info("Markdown optimizing 初始化完成")

    async def optimize(self, markdown: str) -> str:
        if not markdown.strip():
            return ""
        # 调用
        optimized = await self._client.ainvoke(_messages(markdown))
        # 格式化结果并返回
        optimized = optimized.content.strip()
        if not optimized:
            raise RuntimeError("LLM returned empty optimized Markdown")
        return optimized

def _messages(markdown: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": MARKDOWN_OPTIMIZATION_PROMPT},
        {"role": "user", "content": markdown},
    ]
