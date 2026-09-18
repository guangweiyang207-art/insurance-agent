from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from .crud import ChatThreadService
from .exceptions import ChatThreadNotFound
from .schemas import ChatThreadResponse, ChatThreadCreate, ChatHistoryResponse
from ..core.database import get_db
from ..core.logging import get_logger
from ..agent.service import get_message_history, delete_message_history
from ..security.jwt import get_current_user, UserContext
logger = get_logger(__name__)

# 定义router
router = APIRouter(prefix="/chat-threads")

# 定义依赖注入函数，返回值是ChatThreadService，而这个函数又依赖get_db这个函数来获取session
def get_thread_service(db: AsyncSession = Depends(get_db)) -> ChatThreadService:
    return ChatThreadService(db)


def get_agent(request: Request) -> CompiledStateGraph:
    return request.app.state.agent

# 定义接口
@router.post("", response_model=ChatThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_thread(
    body: ChatThreadCreate,
    chat_thread_service: ChatThreadService = Depends(get_thread_service),
    user_info:UserContext = Depends(get_current_user)
) -> ChatThreadResponse:
    """创建新会话"""
    user_id = user_info.id
    thread = await chat_thread_service.create(user_id, body.title)
    logger.info("会话创建成功~", thread_id=str(thread.id), user_id=user_id)
    return thread


@router.get("", response_model=list[ChatThreadResponse])
async def list_chat_threads(
    chat_thread_service: ChatThreadService = Depends(get_thread_service),
    user_info:UserContext = Depends(get_current_user)
) -> list[ChatThreadResponse]:
    """查询当前用户会话列表"""
    return await chat_thread_service.list_by_user(user_info.id)

@router.patch("/{thread_id}")
async def rename_thread(
    thread_id: UUID,
    body: ChatThreadCreate,
    chat_thread_service: ChatThreadService = Depends(get_thread_service),
    user_info:UserContext = Depends(get_current_user)
) -> ChatThreadResponse:
    try:
        user_id = user_info.id
        result = await chat_thread_service.rename(thread_id, user_id, body.title)
        logger.info("会话重命名成功~", thread_id=str(thread_id), user_id=user_id)
        return result
    except ChatThreadNotFound as ex:
        raise _not_found() from ex


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    agent: CompiledStateGraph = Depends(get_agent),
    chat_thread_service: ChatThreadService = Depends(get_thread_service),
    user_info:UserContext = Depends(get_current_user)
):
    try:
        user_id = user_info.id
        # 删除会话；不存在视为已删除，保证接口幂等（重复删除返回 204）
        try:
            await chat_thread_service.delete(thread_id, user_id)
        except ChatThreadNotFound:
            logger.info("delete_thread_already_gone", thread_id=str(thread_id), user_id=user_id)
        # 删除会话历史消息；失败仅记录日志，不影响元数据已删的最终结果
        try:
            await delete_message_history(agent, thread_id)
        except Exception as exc:
            logger.error("delete_message_history_failed", thread_id=str(thread_id), error=type(exc).__name__)

        logger.info("删除会话成功~", thread_id=str(thread_id), user_id=user_id)

    except ChatThreadNotFound as ex:
        raise _not_found() from ex


@router.get("/{thread_id}/messages")
async def get_chat_history(
    thread_id: UUID,
    agent: CompiledStateGraph=Depends(get_agent),
    chat_thread_service: ChatThreadService = Depends(get_thread_service),
    user_info:UserContext = Depends(get_current_user)
):
    user_id = user_info.id
    # 1.校验，当前会话是否属于当前用户
    try:
        await chat_thread_service.required_owner(thread_id, user_id)
    except ChatThreadNotFound as ex:
        raise _not_found() from ex
    # 2.查询会话历史
    messages = await get_message_history(agent, str(thread_id))
    # 3.封装结果
    return ChatHistoryResponse(
        thread_id = thread_id,
        messages=messages
    )



# 定义通用的404异常方法
def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="chat thread not found")
