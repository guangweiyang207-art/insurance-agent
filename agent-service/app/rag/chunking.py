from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from .models import KnowledgeChunk
from ..core.logging import get_logger
logger = get_logger(__name__)

class MarkdownChunker:
    """先按 Markdown 标题生成父块，再在每个父块内部递归生成子块。"""

    def __init__(
        self,
        *,
        child_target_chars: int = 500,
        child_overlap_chars: int = 80,
    ) -> None:
        # overlap 必须小于目标长度，否则递归切分器无法正常前进。
        if child_target_chars <= 0:
            raise ValueError("child_target_chars must be positive")
        if child_overlap_chars < 0:
            raise ValueError("child_overlap_chars must be non-negative")
        if child_overlap_chars >= child_target_chars:
            raise ValueError("child_overlap_chars must be smaller than child_target_chars")

        # 初始化文档结构感知切分器
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
            ],
            strip_headers=True,
        )

        # 初始化递归切分器
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_target_chars,
            chunk_overlap=child_overlap_chars,
            separators=["\n\n", "\n", "。", "；", ";", "，", ","],
            keep_separator="end",
        )
        logger.info("document splitter 初始化完成")

    def chunk(
        self,
        *,
        markdown: str,
        clause_id: int | None = None,
    ) -> tuple[list[KnowledgeChunk], list[KnowledgeChunk]]:
        """为一份 Markdown 文档生成一一关联的父块和子块。"""

        # 使用Markdown结构感知切分，得到小节信息
        sections = self.markdown_splitter.split_text(markdown)

        # 进一步处理，形成 parent_chunks 和 child_chunks
        parent_chunks: list[KnowledgeChunk] = []
        child_chunks: list[KnowledgeChunk] = []

        # 遍历小节
        for section in sections:
            # 生成章节路径（按 h1→h4 顺序，过滤空值，无标题时回退"全文"）
            section_path = _section_path_from_metadata(section.metadata)
            # 标题含有条款名，必须拼接标题到块头部，保证语言完整性
            parent_content = _prepend_section_headings(section.page_content, section_path)
            # 组织 parent_chunk
            parent = KnowledgeChunk(
                id=uuid4(),
                clause_id=clause_id,
                content=parent_content,
                section_path=section_path,
            )
            parent_chunks.append(parent)

            # 切分父的content，生成child_chunk
            for _text in self.child_splitter.split_text(section.page_content.strip()):
                child_text = _text.strip()
                if not child_text:
                    continue
                # 子块继承父块元数据，用更短的文本参与向量检索。
                child = KnowledgeChunk(
                    id=uuid4(),
                    clause_id=clause_id,
                    parent_id=parent.id,
                    section_path=parent.section_path,
                    content=_prepend_section_headings(child_text,section_path),
                )
                child_chunks.append(child)

        return parent_chunks, child_chunks

def _section_path_from_metadata(metadata: dict[str, Any]) -> list[str]:
    """将 LangChain 的标题元数据转换为章节路径。"""

    section_path = [
        str(metadata[key]).strip()
        for key in ["h1", "h2", "h3", "h4"]
        if metadata.get(key) and str(metadata[key]).strip()
    ]
    return section_path or ["全文"]

def _prepend_section_headings(content: str, section_path: list) -> str:
    """把标题链拼接到块首，让每个块都保留完整章节语境。"""
    body = content.strip()
    if not body:
        return ""
    headers = "\n".join(
        f"{'#' * level} {title}"
        for level, title in enumerate(section_path, start=1)
    )
    return f"{headers}\n\n{body}"