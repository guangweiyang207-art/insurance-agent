import json
from typing import AsyncGenerator

import pytest
import pytest_asyncio
import httpx
import app.core.logging

from app.core.logging import configure_logging

configure_logging(level="DEBUG")
logger = get_logger(__name__)

user_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJobS1pbnN1cmFuY2UiLCJzdWIiOiIyIiwidXNlcl9pZCI6MiwidXNlcm5hbWUiOiJodWdlIiwidHlwIjoiYWNjZXNzIiwiaWF0IjoxNzgzODUwNjA0LCJleHAiOjE3ODM4NTI0MDR9.06aRfQlnL1Gv3bYeaHXt24_WXZa4PnjpoS-cdlboRrk"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    # 定义一个httpx.AsyncClient
    async with httpx.AsyncClient(
        base_url=settings.business_service_url, # http://192.168.150.101:8001
        timeout=30.0,
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_get_products(client: httpx.AsyncClient):
    """带参数查询，分页查询保险产品"""
    response = await client.request(
        "get",
        "/api/v1/products",
        params={"page": 2, "page_size": 3} # url路径请求参数
    )
    logger.debug(status = response.status_code)
    logger.debug(data_type = type(response.json()))
    logger.debug(data = response.json())


@pytest.mark.asyncio
async def test_login(client: httpx.AsyncClient):
    # 使用client，发送请求
    response = await client.request(
        "post",
        "/api/v1/auth/login",
        json={"username": "huge", "password": "123321"}
    )
    logger.info(response = response.status_code)

    logger.info(json = response.json())

@pytest.mark.asyncio
async def test_get_plans(client: httpx.AsyncClient):
    """查询方案列表"""
    response = await client.request(
        "get",
        "/api/v1/insurance-plans",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    logger.debug(status = response.status_code)
    logger.debug(data_type = type(response.json()))
    logger.debug(data = response.json())


@pytest.mark.asyncio
async def test_get_products(client: httpx.AsyncClient):
    response = await client.request(
        "get",
        "/api/v1/products/1"
    )
    logger.debug(status = response.status_code)
    logger.debug(data_type = type(response.json()))
    logger.debug(data = response.json())