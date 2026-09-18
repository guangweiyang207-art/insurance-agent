from typing import Any

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
from ...clients.biz_client import biz_client
from ...rag import retriever, RetrievedChunk
from ..models import ChatRuntimeContext
from ...core.logging import get_logger
from .models import InsuredProfile, InsuranceCategory

logger = get_logger(__name__)

# 注意：
# tool 是给LLM用的，调用它的是LLM，参数由LLM传递，返回值也会作为ToolMessage交给LLM，如果想更新State，必须返回Command
# tool的返回值只有两种情况：
    # 普通字符串、对象、字典数据，会被LangChain自动封装ToolMessage，交给LLM
    # Command，其中要包含update, update={}, 字典中就是要更新到state的字段，其中必须包含messages，而且要有ToolMessage
# node，是LangGraph用的，调用它的是LangGraph，参数也由LangGraph传递，传入的State，返回的也必须是State

# 用户画像保存
@tool
async def update_insured_profile(
    runtime: ToolRuntime[ChatRuntimeContext],
    insured_profile: InsuredProfile
) -> Command:
    """保存或更新被保人的年龄、年预算和职业，形成用户画像"""
    profile = insured_profile.model_dump()
    return Command(update={
        "insured_profile": profile,
        "messages": [ToolMessage(content="更新成功", tool_call_id=runtime.tool_call_id)]
    })

@tool
async def get_insured_profile(
    runtime: ToolRuntime[ChatRuntimeContext],
) -> Command:
    """查询被保人的画像，包括年龄、年预算和职业。"""
    profile = runtime.state.get("insured_profile", {})
    # 不更新state，所以直接返回结果即可
    return profile

# 查询候选产品
@tool
async def get_candidate_products(
    runtime: ToolRuntime[ChatRuntimeContext],
    categories: list[str] | None,
    premium_min: float | None = None,
):
    """查询候选产品，用于给用户推荐保险产品。
        Args:
            insurance_category: 是保险类型，没有可留空，可选值: medical, critical_illness, accident, life。
            premium_min: 表示产品最低保费的严格上限。
        """
    try:
        # 如果没有传保险分类，就四种都查询
        categories = categories or [c.value for c in InsuranceCategory]
        # 查询
        candidates = await biz_client.list_candidate_products(categories, premium_min = premium_min)
        # 空结果：明确告知 LLM 没有匹配产品，避免其编造产品
        if not candidates:
            return Command(update={
                "candidate_products": candidates,
                "messages": [ToolMessage(
                    content="没有查询到匹配的保险产品。请如实告知用户当前没有符合条件的保险产品，切勿编造产品名称或价格。",
                    tool_call_id=runtime.tool_call_id,
                )]
            })
        # 返回给LLM，更新到state
        return Command(update={
            "candidate_products": candidates,
            "messages": [ToolMessage(content=candidates, tool_call_id=runtime.tool_call_id)]
        })
    except Exception as exc:
        logger.error("recommendation_candidates_load_failed", error=type(exc).__name__)
        return {"error": "候选产品查询失败", "detail": str(exc)}

@tool
async def find_product_by_name(
    runtime: ToolRuntime[ChatRuntimeContext],
    name: str,
) -> Command:
    """根据产品名称或关键词查询产品，返回匹配的产品列表（含 product_id，供后续条款检索使用）。"""
    try:
        result = await biz_client.list_products(product_name=name)
        items = result.get("items", [])
        if not items:
            return Command(update={
                "messages": [ToolMessage(
                    content="没有找到名称匹配的保险产品。请如实告知用户没有该产品，切勿编造。",
                    tool_call_id=runtime.tool_call_id,
                )]
            })
        return Command(update={
            "messages": [ToolMessage(content=items, tool_call_id=runtime.tool_call_id)]
        })
    except Exception as exc:
        logger.error("find_product_by_name_failed", error=type(exc).__name__)
        return {"error": "产品查询失败", "detail": str(exc)}

@tool
async def search_insurance_knowledge(
    runtime: ToolRuntime[ChatRuntimeContext],
    query: str,
    product_id: int,
    top_k: int = 5,
) -> str:
    """检索保险产品条款，返回回答证据和可追溯引用来源。"""
    try:
        # 检索
        evidences: list[RetrievedChunk] = await retriever().search(query, product_id, top_k)

        # 空结果：明确告知 LLM 没有检索到，避免其编造条款内容
        if not evidences:
            return Command(update={
                'additional_info': {},
                'messages': [ToolMessage(
                    content="未检索到相关条款内容。请如实告知用户：当前知识库中没有该产品对应的条款信息，无法回答，切勿编造条款内容。",
                    tool_call_id=runtime.tool_call_id,
                )]
            })

        # 组织检索到的条款内容，去掉无关信息
        clauses = [] # 给AI用
        sources = {} # 给前端用
        for r in evidences:
            clauses.append({"content": r.content, "source_id": r.source_id})
            sources[r.source_id] = r

        # 把sources写到自定义事件中
        writer = get_stream_writer()
        writer({"type": "additional_info", "data": sources})

        return Command(
            update={
                'additional_info': sources,
                'messages': [ToolMessage(content={"clauses": clauses}, tool_call_id=runtime.tool_call_id)]
            }
        )

    except Exception as exc:
        logger.error("recommendation_plan_knowledge_search_failed", product_id=product_id, error=type(exc).__name__)
        return {"error": "保险条款检索失败", "detail": str(exc)}


@tool
async def search_knowledge_by_product_name(
    runtime: ToolRuntime[ChatRuntimeContext],
    product_name: str,
    query: str,
    top_k: int = 5,
) -> Command:
    """根据产品名称检索该产品的保险条款。自动用产品名查 product_id 再检索，回答条款问题时优先用这个工具。"""
    try:
        products = await biz_client.list_products(product_name=product_name)
        items = products.get("items", [])
        if not items:
            return Command(update={
                'additional_info': {},
                'messages': [ToolMessage(
                    content=f"没有找到名称匹配「{product_name}」的保险产品。请如实告知用户没有该产品，切勿编造。",
                    tool_call_id=runtime.tool_call_id,
                )]
            })
        product_id = items[0]["id"]

        evidences = await retriever().search(query, product_id, top_k)
        if not evidences:
            return Command(update={
                'additional_info': {},
                'messages': [ToolMessage(
                    content=f"产品「{items[0].get('name', product_name)}」没有检索到相关条款内容，请如实告知用户。",
                    tool_call_id=runtime.tool_call_id,
                )]
            })

        clauses = []
        sources = {}
        for r in evidences:
            clauses.append({"content": r.content, "source_id": r.source_id})
            sources[r.source_id] = r
        writer = get_stream_writer()
        writer({"type": "additional_info", "data": sources})
        return Command(update={
            'additional_info': sources,
            'messages': [ToolMessage(content={"clauses": clauses}, tool_call_id=runtime.tool_call_id)]
        })
    except Exception as exc:
        logger.error("search_knowledge_by_product_name_failed", error=type(exc).__name__)
        return {"error": "条款检索失败", "detail": str(exc)}


tools = [
    update_insured_profile,
    get_insured_profile,
    get_candidate_products,
    find_product_by_name,
    search_knowledge_by_product_name,
    search_insurance_knowledge,
]