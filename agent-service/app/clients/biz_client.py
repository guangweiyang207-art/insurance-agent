from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import httpx

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class BusinessServiceError(RuntimeError):
    """biz-service 返回错误时抛出"""

    def __init__(self, status_code: int, body: Any, message: str | None = None) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(message or f"business-service returned HTTP {status_code}")


class BusinessServiceClient:
    """biz-service HTTP 客户端，封装连接池生命周期与业务 API"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def init(self) -> None:
        """初始化连接池，应在应用启动时调用"""
        if not settings.business_service_url:
            raise RuntimeError("business_service_url 未配置，biz-service 客户端初始化失败！")
        self._client = httpx.AsyncClient(
            base_url=settings.business_service_url,
            timeout=10.0,
        )
        logger.info("biz_client_initialized", base_url=settings.business_service_url)

    async def close(self) -> None:
        """关闭连接池，应在应用关闭时调用"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("biz_client_closed")

    # ────────────────────── 商品 ──────────────────────
    async def list_products(
        self,
        *,
        category: str | None = None,
        product_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询所有保险产品"""
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }
        if category:
            params["category"] = category
        if product_name:
            params["product_name"] = product_name
        return await self._request("GET", "/api/v1/products", params=params)

    async def list_candidate_products(
        self,
        categories: list[str],
        *,
        premium_min: float | None = None,
        limit_per_category: int = 5,
    ) -> list[dict[str, Any]]:
        """根据分类列表获取候选商品，可按最低保费过滤"""
        params: dict[str, Any] = {
            "categories": categories,
            "limit_per_category": limit_per_category,
        }
        if premium_min is not None:
            params["premium_min"] = premium_min
        response = await self._request(
            "GET",
            "/api/v1/products/candidates",
            params=params)
        return response.get("data", [])

    async def list_clauses_of_product(
        self,
        *,
        product_id: int = 20,
    ) -> dict[str, Any]:
        """查询指定保险产品的条款"""
        return await self._request(
            "GET",
            f"/api/v1/products/{product_id}/clauses"
        )

    # ─────────────────── 保费试算 ─────────────────────

    async def calculate_premium(
        self,
        user_token: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """根据用户选择的费率因子计算保费"""
        return await self._request(
            "POST",
            "/api/v1/premium/calculate",
            user_token=user_token,
            json=payload,
        )

    # ─────────────────── 投保方案 ─────────────────────

    async def save_current_insurance_plan(
        self,
        user_token: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """保存或更新用户当前的投保方案"""
        return await self._request(
            "PUT",
            "/api/v1/insurance-plans/current",
            user_token=user_token,
            json=payload,
        )

    async def get_current_insurance_plan(self, user_token: str) -> dict[str, Any]:
        """获取用户当前的投保方案"""
        return await self._request(
            "GET",
            "/api/v1/insurance-plans/current",
            user_token=user_token,
        )


    # ────────────────────── 保单 ──────────────────────

    async def list_policies(
        self,
        user_token: str,
        *,
        status: str = "active",
    ) -> dict[str, Any]:
        """查询用户的保单列表，默认只返回有效保单"""
        return await self._request(
            "GET",
            "/api/v1/policies",
            user_token=user_token,
            params={"status": status},
        )

    # ────────────────────── 理赔 ──────────────────────

    async def get_claim_guide(self, user_token: str, policy_id: str | UUID) -> dict[str, Any]:
        """获取指定保单的理赔指引"""
        return await self._request(
            "GET",
            f"/api/v1/claim-guides/{policy_id}",
            user_token=user_token,
        )

    async def list_claims(
        self,
        user_token: str,
        *,
        policy_id: str | UUID | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """查询理赔记录列表，可按保单和状态筛选"""
        params: dict[str, Any] = {}
        if policy_id is not None:
            params["policy_id"] = str(policy_id)
        if status:
            params["status"] = status
        return await self._request("GET", "/api/v1/claims", user_token=user_token, params=params)

    async def get_claim(self, user_token: str, claim_id: str | UUID) -> dict[str, Any]:
        """根据理赔 ID 查询理赔详情"""
        return await self._request("GET", f"/api/v1/claims/{claim_id}", user_token=user_token)

    # ─────────────────── 内部实现 ─────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_token: str | None = None,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 HTTP 请求到 biz-service，自动处理认证和错误"""
        headers = {"Authorization": f"Bearer {user_token}"} if user_token else {}
        assert self._client is not None, "客户端尚未初始化，请先调用 init()"
        response = await self._client.request(
            method, path, headers=headers, json=json, params=params
        )
        if response.status_code >= 400:
            raise BusinessServiceError(response.status_code, _response_body(response))
        body = _response_body(response)
        return body if isinstance(body, dict) else {"data": body}


def _response_body(response: httpx.Response) -> Any:
    """安全解析响应体，JSON 解析失败时返回原始文本"""
    try:
        return response.json()
    except ValueError:
        return response.text


# 模块级单例，import 即用
biz_client = BusinessServiceClient()