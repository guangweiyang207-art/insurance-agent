# biz-service

Python + FastAPI 版本的业务端服务，复用 `insurance_biz` 数据库表和接口路径。

## 运行

```powershell
cd biz-service
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

默认连接：

```text
postgresql://insurance:insurance123@192.168.150.101:5432/insurance_biz
```

可通过环境变量覆盖：

```text
BUSINESS_DATABASE_URL
SERVER_PORT
JWT_ISSUER
JWT_SECRET
JWT_ACCESS_TOKEN_MINUTES
JWT_REFRESH_TOKEN_DAYS
REFRESH_TOKEN_COOKIE_NAME
REFRESH_TOKEN_COOKIE_SECURE
REFRESH_TOKEN_COOKIE_SAMESITE
APP_WORKSPACE_ROOT
```

健康检查：

```text
GET http://localhost:8001/api/v1/health
```

## 说明

本服务目标是教学友好和接口兼容，不负责数据库 schema 迁移。初始化数据库仍使用项目已有 SQL/Flyway 脚本。
