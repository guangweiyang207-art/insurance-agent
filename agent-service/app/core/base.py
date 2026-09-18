# app/core/base.py

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from sqlalchemy import DateTime, func

# 数据校验的基类
class BaseSchema(BaseModel):
    # 可以让BaseModel校验字段时不仅可以基于dict获取属性，还可以基于类的字段来获取属性
    # 因此只要类A和类B的属性一样，就可以把类A的对象直接赋值给类B
    model_config = ConfigDict(from_attributes=True)

# SQLAlchemy的基类，所有数据库表模型都必须继承
class Base(DeclarativeBase):
    pass

# 通用的时间戳【混入类】，这样其它数据模型不用重复定义时间字段
class TimestampMixin:
    # func.now() 会让数据库在插入时自动生成服务器时间（如 PostgreSQL 的 NOW()）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # onupdate=func.now() 会在每次数据行被 UPDATE 时，由 SQLAlchemy 自动更新该字段
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    def __repr__(self) -> str:
        cls_name = self.__class__.__name__
        attrs = {}
        for key, val in vars(self).items():
            if key.startswith("_"):
                continue
            if isinstance(val, datetime):
                attrs[key] = val.strftime("%Y-%m-%d %H:%M:%S")
            else:
                attrs[key] = val
        return f"{cls_name}({attrs})"