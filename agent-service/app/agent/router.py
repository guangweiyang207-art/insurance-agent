import asyncio
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.params import Depends
from fastapi.sse import format_sse_event
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import ChatRequest
from .service import chat_stream
from ..chat_thread.crud import ChatThreadService
from ..chat_thread.exceptions import ChatThreadNotFound
from ..core.database import get_db
from ..security.jwt import get_current_user, UserContext
from ..core.logging import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/chat")

def get_agent(request: Request) -> CompiledStateGraph:
    return request.app.state.agent
def get_thread_service(db: AsyncSession = Depends(get_db)) -> ChatThreadService:
    return ChatThreadService(db)
#实现SSE，返回用yield
@router.post("", response_class=StreamingResponse)
async def chat(
    body: ChatRequest,
    agent: CompiledStateGraph=Depends(get_agent),
    chat_thread_service: ChatThreadService = Depends(get_thread_service),
    user_info: UserContext = Depends(get_current_user)
):
    # 1.参数校验
    message = body.message
    decision = body.decision

    if message is None and decision is None:
        raise HTTPException(status_code=400, detail="Missing message or decision")
    if message is not None and decision is not None:
        raise HTTPException(status_code=400, detail="Send either message or decision")
    if message is not None:
        message = message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message must not be empty")

    if body.thread_id is None:
        raise HTTPException(status_code=400, detail="Missing thread_id")
    # 校验会话归属，防止越权访问他人会话
    try:
        await chat_thread_service.touch(body.thread_id, user_info.id)
    except ChatThreadNotFound as ex:
        raise HTTPException(status_code=404, detail="chat thread not found") from ex
    # 校验在开始 SSE 响应前完成，异常才能作为正常 HTTP 错误返回。
    return StreamingResponse(
        _stream_events(agent, str(body.thread_id), message or '', decision, user_info),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

#SSE 事件封装
def _encode_event(event: str, data) -> str:
    return format_sse_event(
        event=event,
        data_str=json.dumps(jsonable_encoder(data), ensure_ascii=False),
    )


async def _stream_events(agent, thread_id, message, decision, user_info):
    stream = chat_stream(agent, thread_id, message, decision, user_info)
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(anext(stream), timeout=60)
            except StopAsyncIteration:
                break
            yield _encode_event(chunk['event'], chunk['data'])
    except TimeoutError:
        logger.warning("chat_stream_timeout", thread_id=thread_id)
        yield _encode_event("error", {"message": "回复等待超时，请稍后重试。"})
    except Exception as exc:
        # 只记录异常类型，不打印完整堆栈，避免泄露用户对话内容
        logger.error("chat_stream_failed", thread_id=thread_id, error=type(exc).__name__)
        yield _encode_event("error", {"message": "对话暂时失败，请重试。已保存的历史不会删除。"})
    finally:
        await stream.aclose()

