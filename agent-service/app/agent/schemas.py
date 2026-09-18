from __future__ import annotations

from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: UUID
    message: Optional[str] = None # 用户输入
    decision: Optional[dict[str, Any]] = None # HITL人的回复