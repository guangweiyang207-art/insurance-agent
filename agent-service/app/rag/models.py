from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..core.base import Base, BaseSchema

class KnowledgeDocument(BaseModel):
    """一份进入知识库构建流程的文档。"""
    clause_id: int | None = None
    document_name: str
    source_uri: str
    product_ids: list[int] = Field(default_factory=lambda: [-1])

class KnowledgeChunk(BaseSchema):
    """父块和子块共用的数据结构。"""
    id: UUID
    clause_id: int
    content: str
    parent_id: UUID | None = None
    section_path: list[str] = Field(default_factory=list)

#三张表
class DocumentTable(Base):
    __tablename__ = "document"
    clause_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    document_name: Mapped[str | None] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

class ParentChunkTable(Base):
    __tablename__ = "parent_chunks"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    clause_id: Mapped[int | None] = mapped_column(BigInteger)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

class ChildChunkTable(Base):
    __tablename__ = "child_chunks"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    clause_id: Mapped[int | None] = mapped_column(BigInteger)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    section_path: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )