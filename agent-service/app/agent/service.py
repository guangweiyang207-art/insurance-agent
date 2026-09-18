from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import uuid4

from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot

from .models import ChatRuntimeContext
from ..chat_thread.schemas import ChatHistoryMessage
from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..security.jwt import UserContext

logger = get_logger(__name__)


async def chat_stream(
    agent: CompiledStateGraph,
    thread_id: str,
    message: str,
    decision: dict,
    user: UserContext
):
    """同时转发模型 token 和节点直接回复，完成 checkpoint 后才通知前端结束。"""
    thread_id = str(thread_id)
    config = {'configurable': {'thread_id': thread_id}}
    _input = (
        Command(resume=decision)
        if decision is not None
        else {'messages': [HumanMessage(content=message, id=str(uuid4()))], 'additional_info': None}
    )
    additional_info = None
    streamed: dict[str, str] = {}
    emitted_reply = False
    interrupted = False

    def completed_text(item: BaseMessage) -> str:
        if not _is_visible_assistant(item):
            return ''
        text = _content_text(item.content)
        key = item.id or f'text:{text}'
        previous = streamed.get(key, '')
        # A subgraph emits both its tokens and its complete state to the parent.
        # The same message must appear only once in the browser.
        if key in streamed:
            suffix = text[len(previous):] if text.startswith(previous) else ''
        else:
            suffix = text
        streamed[key] = text
        return suffix

    try:
        previous_state = await agent.aget_state(config)
        for item in previous_state.values.get('messages', []):
            if isinstance(item, AIMessage):
                text = _content_text(item.content)
                streamed[item.id or f'text:{text}'] = text

        # astream is an async iterator. This API works with the installed
        # LangGraph 1.1.x; astream_events(version='v3') does not.
        async for namespace, mode, data in agent.astream(
            _input,
            config,
            context=ChatRuntimeContext(user_id=user.id, token=user.token),
            stream_mode=['messages', 'updates', 'custom'],
            subgraphs=True,
            durability='sync',
        ):
            if mode == 'messages':
                item, metadata = data
                if (
                    metadata.get('langgraph_node') == 'route'
                    or 'internal_intent' in metadata.get('tags', [])
                    or not _is_visible_assistant(item)
                ):
                    continue
                if isinstance(item, AIMessageChunk):
                    text = _content_text(item.content)
                    key = item.id or f'node:{namespace}:{metadata.get("langgraph_node")}'
                    streamed[key] = streamed.get(key, '') + text
                else:
                    text = completed_text(item)
                if text:
                    emitted_reply = True
                    yield {'event': 'message', 'data': text}
            elif mode == 'updates' and isinstance(data, dict):
                for node, update in data.items():
                    if node == '__interrupt__':
                        interrupted = True
                        yield {'event': 'interrupt', 'data': [item.value for item in update]}
                        continue
                    if not isinstance(update, dict):
                        continue
                    if update.get('additional_info') is not None:
                        additional_info = update['additional_info']
                    messages = update.get('messages', [])
                    if isinstance(messages, BaseMessage):
                        messages = [messages]
                    for item in messages:
                        text = completed_text(item)
                        if text:
                            emitted_reply = True
                            yield {'event': 'message', 'data': text}
            elif mode == 'custom' and isinstance(data, dict):
                if data.get('type') == 'additional_info':
                    additional_info = data.get('data')
    except TimeoutError:
        logger.warning('chat_stream_timeout', thread_id=thread_id)
        yield {'event': 'error', 'data': {'message': '回复等待超时，请稍后重试。'}}
        return
    except Exception as exc:
        logger.error('chat_stream_failed', thread_id=thread_id, error=type(exc).__name__)
        yield {'event': 'error', 'data': {'message': '对话生成失败，请稍后重试。'}}
        return

    if not emitted_reply and not interrupted:
        yield {'event': 'error', 'data': {'message': '暂时未生成回复，请重新发送消息。'}}
        return
    if additional_info is not None:
        yield {'event': 'additional_info', 'data': additional_info}
    yield {'event': 'done', 'data': {'thread_id': thread_id, 'finish': 'interrupt' if interrupted else 'stop'}}


async def delete_message_history(agent: CompiledStateGraph, thread_id: str):
    """删除会话历史"""
    await agent.checkpointer.adelete_thread(str(thread_id))


async def get_message_history(agent: CompiledStateGraph, thread_id: str) -> list[ChatHistoryMessage]:
    config = {'configurable': {'thread_id': str(thread_id)}}
    latest_messages: list[BaseMessage] | None = None
    additional_by_message: dict[str, Any] = {}
    # The latest checkpoint also contains a user turn interrupted by an error.
    # Read snapshots incrementally instead of retaining every full conversation.
    async for snapshot in agent.aget_state_history(config):
        values = snapshot.values if isinstance(snapshot.values, dict) else {}
        if latest_messages is None:
            latest_messages = list(values.get('messages', []))
        info = _snapshot_additional_info(snapshot)
        if info is not None:
            key, value = info
            additional_by_message.setdefault(key, value)
    return _project_history(latest_messages or [], additional_by_message)


def _message_text(content: str | list[str | dict[str, Any]]) -> str:
    return _content_text(content).strip()


def _content_text(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") in {None, "text"}:
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _project_history_from_snapshots(snapshots: list[StateSnapshot]) -> list[ChatHistoryMessage]:
    """从按时间正序的快照恢复最新历史，将拓展信息归属到对应轮次。"""
    if not snapshots:
        return []
    additional_by_message: dict[str, Any] = {}
    for snapshot in snapshots:
        info = _snapshot_additional_info(snapshot)
        if info is not None:
            additional_by_message[info[0]] = info[1]
    values = snapshots[-1].values
    messages = values.get('messages', []) if isinstance(values, dict) else []
    return _project_history(messages, additional_by_message)


def _snapshot_additional_info(snapshot: StateSnapshot) -> tuple[str, Any] | None:
    values = snapshot.values if isinstance(snapshot.values, dict) else {}
    additional_info = values.get('additional_info')
    if additional_info is None:
        return None
    messages = values.get('messages', [])
    # Stop at this turn's user message. A tool result before the new reply must
    # never attach this turn's sources to the preceding turn's assistant.
    for index in range(len(messages) - 1, -1, -1):
        item = messages[index]
        if isinstance(item, HumanMessage):
            break
        if _is_visible_assistant(item) and _message_text(item.content):
            return _history_message_key(item, index), additional_info
    return None


def _history_message_key(message: BaseMessage, index: int) -> str:
    return message.id or f'index:{index}'


def _is_visible_assistant(message: BaseMessage) -> bool:
    return (
        isinstance(message, AIMessage)
        and not message.tool_calls
        and not message.additional_kwargs.get('tool_calls')
        and not getattr(message, 'tool_call_chunks', None)
    )


def _project_history(
    messages: list[BaseMessage], additional_by_message: dict[str, Any] | None = None,
) -> list[ChatHistoryMessage]:
    """把完整 LangGraph 消息投影为前端可展示的用户和最终助手文本。"""
    projected: list[ChatHistoryMessage] = []
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            role = "user"
        elif _is_visible_assistant(message):
            role = "assistant"
        else:
            continue

        content = _message_text(message.content)
        if content:
            additional_info = (additional_by_message or {}).get(_history_message_key(message, index))
            projected.append(ChatHistoryMessage(role=role, content=content, additional_info=additional_info))
    return projected
