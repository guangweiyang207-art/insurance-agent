from langchain_core.messages import AIMessage, BaseMessage
from langgraph.constants import START, END
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from .models import ChatRuntimeContext, ParentState, RouteResult, Intent
from ..clients.biz_client import biz_client
from ..core.logging import get_logger
from .chitchat import Chitchat
from .recommendation.graph import Recommendation

from .intent_identify import intent_router

logger = get_logger(__name__)


async def _route_node(state: ParentState) -> Command:
    # 在state获取用户消息
    messages = state['messages']
    user_message = messages[-1].content
    # 上下文信息，比如拿AI返回的最后一条消息
    previous_ai_message = _previous_ai_message(messages)
    payload = {}
    if previous_ai_message:
        payload["conversation_history"] = [
            {"role": "assistant", "content": previous_ai_message},
            {"role": "user", "content": user_message},
        ]
    # 意图识别
    route_info = await intent_router.route(user_message, payload)
    # 判断是否是str，如果是，说明是寒暄，直接返回结果，然后END
    if isinstance(route_info, str):
        return Command(
            update={"messages": [AIMessage(content=route_info)]},
            goto=END
        )
    # 如果不是str，才去路由，到子 workflow
    # previous_workflow：就是更新前的active_workflow
    # active_workflow：是正要路由去的workflow
    previous_workflow = state.get('active_workflow', '')
    logger.info(f"previous_workflow: {previous_workflow}, active_workflow: {route_info.intent}")
    return Command(
        update={"route_info": route_info, "active_workflow": route_info.intent, "previous_workflow": previous_workflow},
        goto=route_info.intent
    )

async def _claim_node(state: ParentState, runtime: Runtime[ChatRuntimeContext]):
    """理赔咨询：查询用户保单并引导理赔。"""
    token = runtime.context.token
    try:
        policies = await biz_client.list_policies(token)
        items = policies.get("items", []) if isinstance(policies, dict) else []
        if not items:
            text = "您当前没有有效的保单。如需理赔，请先投保，或直接告诉我您要咨询的理赔问题。"
        else:
            writer = get_stream_writer()
            writer({"type": "additional_info", "data": {"type": "policies", "title": "您的保单", "policies": items}})
            lines = ["您有以下保单："]
            for p in items:
                product = p.get("product") or {}
                lines.append(
                    f"- {product.get('name', '未知产品')}（保单号：{p.get('policy_number', '')}，状态：{p.get('status', '')}）"
                )
            text = "\n".join(lines) + "\n请问您需要对哪份保单办理理赔？"
    except Exception as exc:
        logger.error("claim_policies_load_failed", error=type(exc).__name__)
        text = "抱歉，查询您的保单时出现问题，请稍后重试。"
    return {"messages": [AIMessage(text)]}


async def _handoff_node(state: ParentState):
    # 人工转接：暂无外部客服系统，返回转接说明
    return {"messages": [AIMessage("好的，已记录您的人工服务请求，客服人员会尽快与您联系。")]}


async def _fallback_node(state: ParentState):
    # 返回路由结果
    return {"messages": [AIMessage("信息不足，无法确定你的意图")]}


async def create_agent(checkpointer):
    # 4.创建Graph
    builder = StateGraph(state_schema=ParentState, context_schema=ChatRuntimeContext)
    builder.add_node('route', _route_node)
    builder.add_node('chitchat', Chitchat().build_graph())
    builder.add_node('recommendation_plan', Recommendation().build_graph())
    builder.add_node('claim', _claim_node)
    builder.add_node('human_handoff', _handoff_node)
    builder.add_node('fallback', _fallback_node)

    builder.add_edge(START, 'route')
    builder.add_edge('recommendation_plan', END)
    builder.add_edge('claim', END)
    builder.add_edge('chitchat', END)
    builder.add_edge('human_handoff', END)
    builder.add_edge('fallback', END)

    return builder.compile(checkpointer=checkpointer)


def _previous_ai_message(messages: list[BaseMessage]) -> str | None:
    """返回本轮用户消息之前最近一条可展示的 AI 文本。"""
    for item in reversed(messages):
        if not isinstance(item, AIMessage):
            continue
        if item.tool_calls or item.additional_kwargs.get("tool_calls"):
            continue
        content = item.content
        if content:
            return content
    return None
