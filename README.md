# 安心保智能保险顾问（hm-insurance）

基于 **LangGraph 多智能体 + RAG** 的保险智能客服系统。支持多轮对话、条款级可溯源问答、产品推荐与保费试算，打通「咨询 → 推荐 → 确认」完整业务链路。

## ✨ 功能特性

- **多智能体对话**：父图意图路由 + 子图（闲聊 / 保险推荐）双层 StateGraph，意图识别采用 Pydantic 结构化输出
- **RAG 条款检索**：BGE-M3 稠密+稀疏混合检索、RRF 融合排序、父子块分块、父块回查，回答附带 `[ref-xxx]` 条款引用可溯源
- **防幻觉设计**：检索空结果明确提示、相似度阈值过滤低相关块、system prompt 约束"绝不编造"
- **SSE 流式输出**：逐 token 推送 + 条款引用事件，前端 fetch Reader 手写 SSE 分帧解析
- **会话持久化**：LangGraph Checkpointer 落 PostgreSQL，多轮记忆、历史恢复
- **Redis 缓存加速**：检索结果缓存（TTL 1 小时），高频问题命中缓存跳过向量化与检索，响应从秒级降到毫秒级
- **可观测与评测**：LangSmith 追踪链路、RAGAS 评测检索质量（faithfulness 0.88）

## 🏗️ 系统架构

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   frontend   │───▶│   agent-service   │───▶│   biz-service   │
│  React+Vite  │    │  LangGraph + RAG  │    │  FastAPI 业务    │
│   (5173)     │    │     (8002)        │    │     (8001)       │
└─────────────┘    └────┬────────┬──────┘    └────────┬────────┘
                        │        │                    │
                        ▼        ▼                    ▼
                 ┌──────────┐ ┌──────────┐   ┌────────────────┐
                 │  Milvus  │ │PostgreSQL│   │   PostgreSQL   │
                 │  (向量)  │ │ insurance│   │  insurance_biz │
                 └──────────┘ │ _agent   │   └────────────────┘
                              └──────────┘
```

- **agent-service**：智能客服核心。LangGraph 编排意图路由与推荐子图，RAG 检索条款，通过 httpx 调用 biz-service 业务接口。
- **biz-service**：纯业务数据层。产品、保单、理赔、保费试算，读写 PostgreSQL `insurance_biz` 库。
- **存储**：PostgreSQL（业务数据 + 会话 checkpoint）+ Milvus（条款向量）。

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18、Ant Design 5、Vite 6、TypeScript |
| 智能体 | LangGraph、LangChain、Pydantic v2 结构化输出 |
| RAG | Milvus（混合检索）、BGE-M3（稠密+稀疏向量）、FlagEmbedding |
| 后端 | FastAPI、SSE、JWT、asyncio、httpx、structlog |
| 存储 | PostgreSQL（asyncpg / SQLAlchemy 2.0）、Milvus、Redis（检索缓存） |
| 可观测 | LangSmith、RAGAS |
| 模型 | DeepSeek（LLM API）、BGE-M3（本地 embedding）、MinerU（文档解析 API） |

## 📁 目录结构

```
hm-insurance/
├── frontend/          # 前端（React + Vite + AntD）
├── biz-service/       # 业务服务（FastAPI）
│   └── app/
│       ├── routers/   # 产品、保单、理赔、保费、认证等接口
│       ├── config.py  # 配置
│       └── security.py# JWT 签发与校验
├── agent-service/     # 智能客服服务（FastAPI + LangGraph）
│   ├── app/
│   │   ├── agent/         # LangGraph 编排（graph.py、意图识别、工具调用）
│   │   │   └── recommendation/  # 保险推荐子图
│   │   ├── rag/           # RAG（pipeline、retrieval、chunking、embedding）
│   │   ├── chat_thread/   # 会话管理
│   │   └── core/          # 配置、日志、数据库
│   └── scripts/       # 知识库构建、RAG 评测等脚本
├── deploy/            # Docker 部署方案（docker-compose、nginx、初始化 SQL）
└── models/            # 本地模型权重（BGE-M3、bge-reranker）
```

## 🚀 快速开始（本地开发）

### 1. 环境准备

- Python 3.12、Node.js、PostgreSQL 16
- 启动 PostgreSQL，初始化 `insurance_biz`、`insurance_agent` 两个库（或用 `deploy/postgres/init/` 下的 SQL）
- （可选）启动 Redis，用于 RAG 检索缓存加速；未启动则自动跳过缓存，功能不受影响
- 下载模型到 `models/`：
  - `BAAI/bge-m3`（embedding）
  - `BAAI/bge-reranker-v2-m3`（重排，可选）
- 在 `agent-service/.env` 和 `biz-service/.env` 配置 DeepSeek API Key、数据库连接等

### 2. 启动三个服务

```bash
# biz-service（8001）
cd biz-service && .venv/Scripts/python.exe -m app.main

# agent-service（8002）
cd agent-service && .venv/Scripts/python.exe -m app.main

# frontend（5173）
cd frontend && npm install && npm run dev
```

浏览器访问 http://localhost:5173，登录账号 `demo` / `demo123`。

### 3. 构建知识库

```bash
cd agent-service
.venv/Scripts/python.exe scripts/ingest_rag_document.py
```

脚本会从 biz-service 拉取产品 → 查主条款 → 去重 → 走 Pipeline（MinerU 解析 PDF → DeepSeek 优化 → 分块 → BGE-M3 向量化）→ 入库 Milvus + PostgreSQL。

## 🐳 Docker 部署

```bash
cd deploy
docker compose up -d
```

编排 PostgreSQL、Milvus（etcd + minio）、biz-service、frontend（nginx）。

## 📊 RAG 评测

```bash
cd agent-service
.venv/Scripts/python.exe -m pip install ragas datasets
.venv/Scripts/python.exe scripts/evaluate_rag.py
```

用 RAGAS 对条款问答做忠实度评测。

## 🔑 环境变量

见 `agent-service/.env.example`、`biz-service/.env.example`、`deploy/.env.example`（需自行创建 `.env`，密钥不入库）。

关键配置项：

| 类别 | 变量 | 说明 |
|---|---|---|
| LLM | `DEEPSEEK_API_KEY`、`CHAT_MODEL` | DeepSeek API（模型 `deepseek-v4-flash`） |
| 数据库 | `DATABASE_URL`、`BUSINESS_DATABASE_URL` | PostgreSQL 连接 |
| 向量库 | `MILVUS_DB_PATH`、`MILVUS_COLLECTION` | Milvus Lite 本地文件 |
| 模型 | `EMBEDDING_MODEL`、`RERANK_MODEL` | 本地 BGE-M3 / reranker 路径 |
| RAG 调优 | `RAG_SIMILARITY_THRESHOLD`、`RAG_QUERY_REWRITE_ENABLE`、`RAG_CANDIDATE_K` | 相似度阈值、查询改写、候选池 |
| 缓存 | `REDIS_URL`、`RAG_CACHE_TTL` | Redis 检索缓存（可选，未配置自动跳过） |
| 可观测 | `LANGSMITH_API_KEY`、`LANGSMITH_TRACING` | LangSmith 追踪 |
