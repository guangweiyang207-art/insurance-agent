from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.config import get_settings
from app.database import db
from app.responses import api_error
from app.security import (
    auth_response,
    create_refresh_token,
    hash_password,
    load_active_user,
    validate_refresh_token,
    verify_password,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(request: RegisterRequest, response: Response) -> dict[str, object]:
    if not request.username.strip():
        raise api_error(400, "INVALID_REGISTER_REQUEST", "用户名不能为空")
    if "@" not in request.email:
        raise api_error(400, "INVALID_REGISTER_REQUEST", "邮箱格式不正确")
    if len(request.password) < 6:
        raise api_error(400, "INVALID_REGISTER_REQUEST", "密码长度至少 6 位")

    exists = db.fetch_one(
        "SELECT COUNT(*) AS count FROM users WHERE username = %s OR email = %s",
        (request.username, request.email),
    )
    if exists and exists["count"] > 0:
        raise api_error(409, "USER_EXISTS", "用户名或邮箱已存在")

    user = db.fetch_one(
        """
        INSERT INTO users (username, email, password_hash, display_name, status)
        VALUES (%s, %s, %s, %s, 'active')
        RETURNING id, username, email, password_hash, display_name, status
        """,
        (request.username, request.email, hash_password(request.password), request.username),
    )
    _set_refresh_cookie(response, user)
    return auth_response(user)


@router.post("/login")
def login(request: LoginRequest, response: Response) -> dict[str, object]:
    if not request.username.strip() or not request.password:
        raise api_error(400, "INVALID_CREDENTIALS", "用户名/邮箱和密码不能为空")
    user = db.fetch_one(
        """
        SELECT id, username, email, password_hash, display_name, status
        FROM users
        WHERE username = %s OR email = %s
        """,
        (request.username, request.username),
    )
    if user is None or user["status"] != "active" or not verify_password(request.password, user["password_hash"]):
        raise api_error(400, "INVALID_CREDENTIALS", "用户名/邮箱或密码错误")
    _set_refresh_cookie(response, user)
    return auth_response(user)


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
) -> dict[str, object]:
    settings = get_settings()
    refresh_token = request.cookies.get(settings.refresh_token_cookie_name)
    if not refresh_token:
        raise api_error(401, "INVALID_REFRESH_TOKEN", "Refresh token is missing")
    payload = validate_refresh_token(refresh_token)
    if payload is None:
        raise api_error(401, "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired")
    user = load_active_user(int(payload["user_id"]))
    _set_refresh_cookie(response, user)
    return auth_response(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, object]:
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path="/",
        samesite=settings.refresh_token_cookie_samesite,
        secure=settings.refresh_token_cookie_secure,
        httponly=True,
    )
    return {"ok": True}


def _set_refresh_cookie(response: Response, user: dict[str, object]) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=create_refresh_token(user),
        max_age=settings.jwt_refresh_token_days * 24 * 60 * 60,
        path="/",
        secure=settings.refresh_token_cookie_secure,
        httponly=True,
        samesite=settings.refresh_token_cookie_samesite,
    )
