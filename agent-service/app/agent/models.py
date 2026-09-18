from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NotRequired

from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
#这是**LangGraph 主图（Parent Graph）的状态定义 + 类型模型**。
# 意图识别常量
Intent = Literal[
    "chitchat",             # 闲聊
    "recommendation_plan",  # 保险推荐和咨询
    "claim",                # 理赔
    "human_handoff",        # 人工
    "fallback",             # 未知
]

# 路由结果，通常路由结果必须说明判断原因和置信度
class RouteResult(BaseModel):
    intent: Intent = Field(description="The best target intent for the current user turn.")
    confidence: float = Field(ge=0, le=1, description="Routing confidence from 0 to 1.")
    reason: str = Field(description="判断用户意图的理由.")

# 主图的State结构
class ParentState(MessagesState):
    route_info: NotRequired[RouteResult]  # 路由信息
    previous_workflow: NotRequired[str]  # 上一个工作流
    active_workflow: NotRequired[str]  # 当前激活的工作流
    additional_info: NotRequired[dict]  # 拓展信息，用于RAG引用溯源

# 上下文信息
@dataclass
class ChatRuntimeContext:
    user_id: str | None
    token: str | None