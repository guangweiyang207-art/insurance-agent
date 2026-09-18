import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic.dataclasses import dataclass

from ..core.config import settings

# FastAPI自带，提取请求头
security = HTTPBearer()


@dataclass(frozen=True, slots=True)
class UserContext:
    id: int
    token: str
    username: str

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """从 HTTP 头提取 JWT → 验签 → 返回用户信息和原始 token"""
    token = credentials.credentials

    try:
        # 解析并校验jwt
        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])

        # 校验签发方与 token 类型，防止 refresh token 被当作 access token 使用
        if payload.get("iss") != settings.jwt_issuer or payload.get("typ") != "access":
            raise HTTPException(status_code=401, detail="无效的认证凭据")

        user_id: int = payload.get("user_id")
        username: str = payload.get("username", '')
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效的认证凭据")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")

    return UserContext(id=user_id, username=username, token=token)