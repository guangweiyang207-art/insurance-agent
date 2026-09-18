# Docker 部署说明

## 一键部署

Windows PowerShell:

```powershell
.\deploy\deploy.ps1
```

Linux/macOS:

```bash
bash deploy/deploy.sh
```

首次运行会从 `deploy/.env.example` 复制生成 `deploy/.env`。真实部署前应修改：

- `JWT_SECRET`
- `POSTGRES_BIZ_PASSWORD`
- `REDIS_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `DEEPSEEK_API_KEY`
- `MINERU_TOKEN`

## 服务地址

| 服务 | 默认地址 |
| --- | --- |
| frontend | `http://localhost:5175` |
| biz-service | `http://localhost:8001` |
| agent-service | `http://localhost:8002` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Milvus | `localhost:19530` |
| MinIO Console | `http://localhost:9001` |



## 数据库初始化

PostgreSQL 首次创建数据卷时会执行：

```text
deploy/postgres/init/
```

- `01-create-agent-database.sql` 创建 `insurance_agent`
- `02-init-biz-schema.sql` 初始化 `insurance_biz`
- `03-init-agent-schema.sql` 初始化 `insurance_agent`

这些脚本只在数据卷第一次创建时运行。已有 `postgres_data` 卷时，修改 SQL 不会自动重新执行。
