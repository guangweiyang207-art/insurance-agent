from ..models import ParentState

from enum import StrEnum
from operator import add
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field

from ..models import ParentState


# 保险类别
class InsuranceCategory(StrEnum):
    MEDICAL = "medical"                     # 医疗险
    CRITICAL_ILLNESS = "critical_illness"   # 重疾险
    ACCIDENT = "accident"                   # 意外险
    LIFE = "life"                           # 寿险

# 被保人信息（用户画像）
class InsuredProfile(BaseModel):
    age: Optional[int] = Field(default=None, description="被保人年龄")
    budget: Optional[float] = Field(default=None, description="年缴保费预算")
    occupation: Optional[str] = Field(default=None, description="职业")

def add_candidate_products(olds: list[dict], news: list[dict]):
    if not olds:
        return news
    merged = {p['id']: p  for p in olds + news}
    return list(merged.values())

class RecommendationPlanState(ParentState):
    """推荐 子agent私有数据"""
    insured_profile: Optional[dict[str, Any]] # 用户画像
    candidate_products: Annotated[list[dict[str, Any]], add_candidate_products] # 候选产品，可以不断累加