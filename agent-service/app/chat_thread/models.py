from sqlalchemy import UUID, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column
from ..core.base import Base, TimestampMixin
import uuid

class ChatThreadTable(Base, TimestampMixin):
    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4, # id基于uuid自动生成，不用自己填写
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新会话")