import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Header

from .config import get_settings
from app.database import db
from .responses import api_error


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_json(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _create_token(user: dict[str, Any], *, token_type: str, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(user["id"]),
        "user_id": user["id"],
        "username": user["username"],
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    signing_input = f"{_b64url_json(header)}.{_b64url_json(payload)}"
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def create_access_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    return _create_token(
        user,
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_minutes),
    )


def create_refresh_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    return _create_token(
        user,
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_days),
    )


def _validate_token(token: str, *, expected_type: str) -> dict[str, Any] | None:
    settings = get_settings()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _b64url(hmac.new(settings.jwt_secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        return None
    try:
        header = json.loads(_decode_b64url(parts[0]))
        payload = json.loads(_decode_b64url(parts[1]))
    except Exception:
        return None
    if header.get("alg") != "HS256" or payload.get("iss") != settings.jwt_issuer:
        return None
    if payload.get("typ") != expected_type:
        return None
    if int(payload.get("exp") or 0) <= int(datetime.now(timezone.utc).timestamp()):
        return None
    return payload


def validate_access_token(token: str) -> dict[str, Any] | None:
    return _validate_token(token, expected_type="access")


def validate_refresh_token(token: str) -> dict[str, Any] | None:
    return _validate_token(token, expected_type="refresh")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def user_summary(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "displayName": user.get("display_name"),
    }


def auth_response(user: dict[str, Any]) -> dict[str, Any]:
    return {"access_token": create_access_token(user), "token_type": "Bearer", "user": user_summary(user)}


def current_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: int | None = Header(default=None, alias="X-User-ID"),
) -> int:
    if x_user_id is not None:
        return x_user_id
    if not authorization or not authorization.startswith("Bearer "):
        raise api_error(401, "UNAUTHORIZED", "Missing authorization token")
    payload = validate_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise api_error(401, "UNAUTHORIZED", "Invalid or expired token")
    return int(payload["user_id"])


def load_active_user(user_id: int) -> dict[str, Any]:
    user = db.fetch_one(
        """
        SELECT id, username, email, password_hash, display_name, status
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )
    if user is None:
        raise api_error(404, "USER_NOT_FOUND", "User not found")
    if user["status"] != "active":
        raise api_error(400, "INACTIVE_USER", "User is inactive")
    return user
