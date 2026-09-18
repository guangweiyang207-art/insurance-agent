from .exceptions import ChatThreadNotFound
from .models import ChatThreadTable
from sqlalchemy import delete, desc, func, select, update, insert, values, asc
from sqlalchemy.ext.asyncio import AsyncSession


class ChatThreadService:
    """管理用户会话数据"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, title: str) -> ChatThreadTable:
        """新增会话"""
        async with self.session.begin():
            # 保存会话并返回结果
            chat_thread = ChatThreadTable(user_id=user_id, title=title)
            self.session.add(chat_thread)
        return chat_thread

    async def list_by_user(self, user_id: int) -> list[ChatThreadTable]:
        """查询当前用户的会话"""
        result = await self.session.execute(
            select(ChatThreadTable)  # select * from chat_thread
            .where(ChatThreadTable.user_id == user_id)  # 根据用户id查询 where user_id = ?
            .order_by(  # order by updated_at desc , created_at desc
                desc(ChatThreadTable.updated_at),
                desc(ChatThreadTable.created_at)
            )  # 默认按照更新时间排序
        )
        return result.scalars().all()

    async def rename(self, thread_id, user_id, title) -> ChatThreadTable:
        """重命名会话"""
        async with self.session.begin():
            # 尝试更新title
            result = await self.session.execute(
                update(ChatThreadTable)
                .values(title=title)
                .where(ChatThreadTable.id == thread_id, ChatThreadTable.user_id == user_id)
                .returning(ChatThreadTable)
            )
            # 判断结果，是否更新成功
            thread = result.scalar_one_or_none()
            if thread is None:
                raise ChatThreadNotFound(f"更新失败，thread_id错误：{thread_id}")
        return thread

    async def delete(self, thread_id, user_id):
        async with self.session.begin():
            # 先查询，校验
            thread = await self.session.get(ChatThreadTable, thread_id)
            if not thread or thread.user_id != user_id:
                raise ChatThreadNotFound(f"删除失败，thread_id错误：{thread_id}")
            # 再删除
            await self.session.delete(thread)

    async def required_owner(self, thread_id, user_id):
        thread = await self.session.get(ChatThreadTable, thread_id)
        if not thread or thread.user_id != user_id:
            raise ChatThreadNotFound(f"非法访问，thread_id错误：{thread_id}")
        return thread

    async def touch(self, thread_id, user_id):
        """在同一事务中校验归属并更新，避免查询隐式开启事务后再次 begin。"""
        async with self.session.begin():
            result = await self.session.execute(
                update(ChatThreadTable)
                .values(updated_at=func.now())
                .where(ChatThreadTable.id == thread_id, ChatThreadTable.user_id == user_id)
                .returning(ChatThreadTable.id)
            )
            if result.scalar_one_or_none() is None:
                raise ChatThreadNotFound(f"chat thread not found: {thread_id}")
