-- Initializes insurance_agent tables owned by agent-service.
\connect insurance_agent

CREATE TABLE IF NOT EXISTS chat_threads (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '新会话',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_threads_user_updated
    ON chat_threads(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id UUID PRIMARY KEY,
    clause_id BIGINT,
    document_type VARCHAR(40) NOT NULL,
    document_name VARCHAR(255) NOT NULL,
    source_uri TEXT NOT NULL,
    version VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'pending_parse',
    checksum VARCHAR(128) NOT NULL,
    parse_provider VARCHAR(80) NOT NULL DEFAULT 'mineru_open_sdk',
    parse_result_uri TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_knowledge_documents_type CHECK (
        document_type IN ('clause', 'product_manual', 'service_manual', 'claim_guide', 'faq')
    ),
    CONSTRAINT chk_knowledge_documents_status CHECK (
        status IN ('pending_parse', 'parsed', 'chunked', 'embedded', 'indexed', 'failed')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_documents_checksum
    ON knowledge_documents(checksum);

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_documents_clause
    ON knowledge_documents(clause_id)
    WHERE clause_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS knowledge_parent_chunks (
    parent_chunk_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES knowledge_documents(document_id),
    clause_id BIGINT,
    section_path TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    section_type VARCHAR(80) NOT NULL DEFAULT 'other',
    clause_no VARCHAR(80),
    page_start INT,
    page_end INT,
    char_start INT,
    char_end INT,
    content TEXT NOT NULL,
    token_count INT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_parent_chunks_document
    ON knowledge_parent_chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_parent_chunks_clause
    ON knowledge_parent_chunks(clause_id);

CREATE TABLE IF NOT EXISTS knowledge_child_chunks (
    child_chunk_id UUID PRIMARY KEY,
    parent_chunk_id UUID NOT NULL REFERENCES knowledge_parent_chunks(parent_chunk_id),
    document_id UUID NOT NULL REFERENCES knowledge_documents(document_id),
    clause_id BIGINT,
    section_path TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    section_type VARCHAR(80) NOT NULL DEFAULT 'other',
    clause_no VARCHAR(80),
    page_start INT,
    page_end INT,
    char_start INT,
    char_end INT,
    content TEXT NOT NULL,
    token_count INT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    milvus_collection VARCHAR(120),
    vector_status VARCHAR(40) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_knowledge_child_chunks_vector_status CHECK (
        vector_status IN ('pending', 'embedded', 'indexed', 'failed', 'disabled')
    )
);

CREATE INDEX IF NOT EXISTS idx_knowledge_child_chunks_parent
    ON knowledge_child_chunks(parent_chunk_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_child_chunks_document
    ON knowledge_child_chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_child_chunks_clause
    ON knowledge_child_chunks(clause_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_child_chunks_vector_status
    ON knowledge_child_chunks(vector_status);

CREATE TABLE IF NOT EXISTS knowledge_ingestion_jobs (
    job_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES knowledge_documents(document_id),
    job_type VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    error_code VARCHAR(80),
    error_message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_knowledge_ingestion_jobs_type CHECK (
        job_type IN ('parse', 'chunk', 'embed', 'index', 'reindex')
    ),
    CONSTRAINT chk_knowledge_ingestion_jobs_status CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_knowledge_ingestion_jobs_document
    ON knowledge_ingestion_jobs(document_id, status);

COMMENT ON TABLE knowledge_documents IS '进入 RAG 构建 Pipeline 的知识文档';
COMMENT ON COLUMN knowledge_documents.document_id IS '知识文档主键';
COMMENT ON COLUMN knowledge_documents.clause_id IS '关联的业务条款主键';
COMMENT ON COLUMN knowledge_documents.document_type IS '文档类型：条款、产品手册、服务手册、理赔指南或 FAQ';
COMMENT ON COLUMN knowledge_documents.document_name IS '文档展示名称';
COMMENT ON COLUMN knowledge_documents.source_uri IS 'MinerU 可读取的原始文件地址';
COMMENT ON COLUMN knowledge_documents.version IS '知识文档版本';
COMMENT ON COLUMN knowledge_documents.status IS '知识构建状态';
COMMENT ON COLUMN knowledge_documents.checksum IS '原始文件内容哈希，用于去重';
COMMENT ON COLUMN knowledge_documents.parse_provider IS '文档解析服务标识';
COMMENT ON COLUMN knowledge_documents.parse_result_uri IS '解析结果地址，当前可为空';
COMMENT ON COLUMN knowledge_documents.metadata IS '文档级扩展元数据';
COMMENT ON COLUMN knowledge_documents.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_documents.updated_at IS '最后更新时间';

COMMENT ON TABLE knowledge_parent_chunks IS '用于完整上下文和引用展示的父知识块';
COMMENT ON COLUMN knowledge_parent_chunks.parent_chunk_id IS '父块主键';
COMMENT ON COLUMN knowledge_parent_chunks.document_id IS '所属知识文档';
COMMENT ON COLUMN knowledge_parent_chunks.clause_id IS '关联的业务条款主键';
COMMENT ON COLUMN knowledge_parent_chunks.section_path IS 'Markdown 标题层级路径';
COMMENT ON COLUMN knowledge_parent_chunks.section_type IS '保险责任、免责、理赔流程等章节类型';
COMMENT ON COLUMN knowledge_parent_chunks.clause_no IS '条款编号';
COMMENT ON COLUMN knowledge_parent_chunks.page_start IS '来源起始页';
COMMENT ON COLUMN knowledge_parent_chunks.page_end IS '来源结束页';
COMMENT ON COLUMN knowledge_parent_chunks.char_start IS '原文起始字符位置，当前预留';
COMMENT ON COLUMN knowledge_parent_chunks.char_end IS '原文结束字符位置，当前预留';
COMMENT ON COLUMN knowledge_parent_chunks.content IS '父块完整正文';
COMMENT ON COLUMN knowledge_parent_chunks.token_count IS '文本 Token 数量';
COMMENT ON COLUMN knowledge_parent_chunks.metadata IS '页码、表格等扩展元数据';
COMMENT ON COLUMN knowledge_parent_chunks.created_at IS '创建时间';

COMMENT ON TABLE knowledge_child_chunks IS '用于 Milvus 精确检索的子知识块';
COMMENT ON COLUMN knowledge_child_chunks.child_chunk_id IS '子块主键，同时用于关联向量记录';
COMMENT ON COLUMN knowledge_child_chunks.parent_chunk_id IS '所属父块';
COMMENT ON COLUMN knowledge_child_chunks.document_id IS '所属知识文档';
COMMENT ON COLUMN knowledge_child_chunks.clause_id IS '关联的业务条款主键';
COMMENT ON COLUMN knowledge_child_chunks.section_path IS 'Markdown 标题层级路径';
COMMENT ON COLUMN knowledge_child_chunks.section_type IS '保险责任、免责、理赔流程等章节类型';
COMMENT ON COLUMN knowledge_child_chunks.clause_no IS '条款编号';
COMMENT ON COLUMN knowledge_child_chunks.page_start IS '来源起始页';
COMMENT ON COLUMN knowledge_child_chunks.page_end IS '来源结束页';
COMMENT ON COLUMN knowledge_child_chunks.char_start IS '原文起始字符位置，当前预留';
COMMENT ON COLUMN knowledge_child_chunks.char_end IS '原文结束字符位置，当前预留';
COMMENT ON COLUMN knowledge_child_chunks.content IS '用于向量检索的子块正文';
COMMENT ON COLUMN knowledge_child_chunks.token_count IS '文本 Token 数量';
COMMENT ON COLUMN knowledge_child_chunks.metadata IS '页码、表格等扩展元数据';
COMMENT ON COLUMN knowledge_child_chunks.milvus_collection IS '写入的 Milvus Collection 名称';
COMMENT ON COLUMN knowledge_child_chunks.vector_status IS '向量化和索引状态';
COMMENT ON COLUMN knowledge_child_chunks.created_at IS '创建时间';

COMMENT ON TABLE knowledge_ingestion_jobs IS '知识库解析、切分、向量化和索引任务记录';
COMMENT ON COLUMN knowledge_ingestion_jobs.job_id IS '构建任务主键';
COMMENT ON COLUMN knowledge_ingestion_jobs.document_id IS '处理的知识文档';
COMMENT ON COLUMN knowledge_ingestion_jobs.job_type IS '任务阶段类型';
COMMENT ON COLUMN knowledge_ingestion_jobs.status IS '任务执行状态';
COMMENT ON COLUMN knowledge_ingestion_jobs.error_code IS '失败错误码';
COMMENT ON COLUMN knowledge_ingestion_jobs.error_message IS '失败错误信息';
COMMENT ON COLUMN knowledge_ingestion_jobs.started_at IS '任务开始时间';
COMMENT ON COLUMN knowledge_ingestion_jobs.finished_at IS '任务结束时间';
COMMENT ON COLUMN knowledge_ingestion_jobs.created_at IS '任务创建时间';

COMMENT ON TABLE chat_threads IS '用户与智能客服的会话元数据，消息正文由 LangGraph Checkpointer 保存';
COMMENT ON COLUMN chat_threads.id IS '会话主键，同时作为 LangGraph thread_id';
COMMENT ON COLUMN chat_threads.user_id IS 'JWT 中解析出的业务用户主键';
COMMENT ON COLUMN chat_threads.title IS '会话列表展示标题';
COMMENT ON COLUMN chat_threads.created_at IS '会话创建时间';
COMMENT ON COLUMN chat_threads.updated_at IS '最后一次对话或修改标题的时间';
