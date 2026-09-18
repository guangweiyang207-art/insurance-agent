-- Initializes insurance_biz tables and demo data.
-- Extracted from the former Java business-service Flyway migrations.

-- ==== V1__baseline.sql ====
CREATE TABLE IF NOT EXISTS app_metadata (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO app_metadata(key, value)
VALUES ('schema', 'business-service-baseline')
ON CONFLICT (key) DO NOTHING;


-- ==== V2__core_schema.sql ====
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(160) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    clause_name VARCHAR(300) NOT NULL,
    category VARCHAR(50) NOT NULL,
    insurer VARCHAR(120) NOT NULL,
    image_url TEXT,
    description TEXT,
    min_premium DECIMAL(14,2),
    max_premium DECIMAL(14,2),
    target_group VARCHAR(300),
    highlights TEXT[],
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_products_category CHECK (category IN ('medical', 'critical_illness', 'accident', 'life'))
);

CREATE TABLE IF NOT EXISTS clauses (
    id BIGSERIAL PRIMARY KEY,
    file_name VARCHAR(300) NOT NULL UNIQUE,
    file_path VARCHAR(500) NOT NULL,
    clause_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_clauses_type CHECK (clause_type IN ('main_clause', 'additional_clause', 'exclusion', 'product_brochure'))
);

CREATE TABLE IF NOT EXISTS product_clauses (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    clause_id BIGINT NOT NULL REFERENCES clauses(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_product_clauses UNIQUE (product_id, clause_id)
);

CREATE TABLE IF NOT EXISTS rate_table_files (
    id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    file_name VARCHAR(300) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),
    parser_version VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    validation_report JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    CONSTRAINT chk_rate_table_files_status CHECK (status IN ('pending', 'parsed', 'validated', 'active', 'failed'))
);

CREATE TABLE IF NOT EXISTS rate_plans (
    id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    plan_code VARCHAR(80) NOT NULL,
    plan_name VARCHAR(200) NOT NULL,
    rate_type VARCHAR(50) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'CNY',
    required_params JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_params JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_rate_plans_product_code UNIQUE (product_id, plan_code),
    CONSTRAINT chk_rate_plans_status CHECK (status IN ('active', 'inactive')),
    CONSTRAINT chk_rate_plans_type CHECK (rate_type IN (
        'fixed_plan_premium',
        'age_band_plan_premium',
        'per_1000_sum_assured',
        'per_10000_sum_assured',
        'coverage_amount_matrix',
        'rider_rate'
    ))
);

CREATE TABLE IF NOT EXISTS rate_table_items (
    id UUID PRIMARY KEY,
    rate_file_id UUID REFERENCES rate_table_files(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    plan_code VARCHAR(80) NOT NULL,
    rate_type VARCHAR(50) NOT NULL,
    age_min INT,
    age_max INT,
    gender VARCHAR(20) NOT NULL DEFAULT 'all',
    occupation_class VARCHAR(20) NOT NULL DEFAULT 'all',
    social_security VARCHAR(20) NOT NULL DEFAULT 'all',
    payment_period VARCHAR(50),
    coverage_period VARCHAR(50),
    coverage_amount DECIMAL(14,2),
    deductible DECIMAL(14,2),
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    rate_value DECIMAL(18,6),
    premium DECIMAL(14,2),
    source_page INT,
    source_table VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_rate_table_items_status CHECK (status IN ('active', 'inactive')),
    CONSTRAINT chk_rate_table_items_gender CHECK (gender IN ('male', 'female', 'unisex', 'all')),
    CONSTRAINT chk_rate_table_items_social_security CHECK (social_security IN ('yes', 'no', 'all')),
    CONSTRAINT chk_rate_table_items_non_negative CHECK (
        (rate_value IS NULL OR rate_value >= 0)
        AND (premium IS NULL OR premium >= 0)
    )
);

CREATE TABLE IF NOT EXISTS premium_quotes (
    id UUID PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    request_params JSONB NOT NULL,
    result JSONB NOT NULL,
    total_premium DECIMAL(14,2) NOT NULL,
    pricing_mode VARCHAR(30) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_premium_quotes_pricing_mode CHECK (pricing_mode IN ('table', 'demo_formula'))
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    thread_id UUID,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    confirmation_id VARCHAR(60) UNIQUE,
    idempotency_key VARCHAR(160) UNIQUE,
    items JSONB NOT NULL,
    quote_ids UUID[] NOT NULL DEFAULT '{}',
    total_premium DECIMAL(14,2) NOT NULL,
    recommendation_snapshot JSONB,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_payment',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_orders_status CHECK (status IN ('pending_payment', 'pending_policy', 'paid', 'completed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    product_id BIGINT REFERENCES products(id),
    claim_type VARCHAR(50) NOT NULL,
    amount DECIMAL(14,2),
    description TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'submitted',
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_claims_type CHECK (claim_type IN ('medical', 'accident', 'critical_illness', 'life')),
    CONSTRAINT chk_claims_status CHECK (status IN ('submitted', 'reviewing', 'approved', 'rejected', 'paid'))
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_clauses_type ON clauses(clause_type);
CREATE INDEX IF NOT EXISTS idx_product_clauses_product ON product_clauses(product_id);
CREATE INDEX IF NOT EXISTS idx_product_clauses_clause ON product_clauses(clause_id);
CREATE INDEX IF NOT EXISTS idx_rate_items_lookup
    ON rate_table_items(product_id, plan_code, age_min, age_max, gender, payment_period, coverage_period, status);
CREATE INDEX IF NOT EXISTS idx_rate_items_dimensions ON rate_table_items USING GIN(dimensions);
CREATE INDEX IF NOT EXISTS idx_premium_quotes_user ON premium_quotes(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_claims_user ON claims(user_id);

-- ==== V3__seed_products_clauses.sql ====
INSERT INTO products (id, name, clause_name, category, insurer, image_url, description, min_premium, max_premium, target_group, highlights)
VALUES
(1, '达尔文宝贝计划12号', '信美相互互联网星辰守护B款少儿重大疾病保险', 'critical_illness', '信美人寿相互保险社', 'https://files.huizecdn.com/file3/M00/91/12/rBYA3Gi1gZ2AXBL7AAYFJxRhbPg411.png', '117种重疾+28种中症+45种轻症，少儿重疾保障灵活。', 285.30, 2501.83, '0-17周岁', ARRAY['117种重疾','少儿保障','可选投保人豁免']),
(2, '达尔文12号重大疾病保险', '复星联合优选K重大疾病保险（互联网）', 'critical_illness', '复星联合健康保险', 'https://files.huizecdn.com/file3/M00/90/E5/rBYA3Gi1BnWALIBtAAYFAsRjzwk030.png', '120种重疾+30种中症+45种轻症，可选多项责任。', 561.00, 4815.00, '28天-35周岁（1-4类职业）', ARRAY['120种重疾','中轻症保障','可选责任丰富']),
(3, '复星联合医联有盟重疾险', '复星联合医联有盟重大疾病保险', 'critical_illness', '复星联合健康保险', 'https://files.huizecdn.com/file3/M00/95/DE/rBYA3GjL0m-AN888AAEX8uDe8d4708.png', '重疾保障产品，含主险及长期医疗附加保障。', 3185.00, 5111.00, '18-59周岁（1-4类职业）', ARRAY['重疾保障','可附加医疗']),
(4, '复星联合星相守2号长期医疗险（个人版）', '复星联合优选二号长期住院医疗保险（费率可调）（互联网）', 'medical', '复星联合健康保险', 'https://files.huizecdn.com/file3/M00/AC/B9/rBYA3GlFEUWAWcX8AAO1o6m75Qg526.png', '免赔额灵活可选，保证续保20年特需，外购药不限清单。', 148.00, 3605.00, '1-55周岁（1-4类职业）', ARRAY['长期医疗','门急诊可选','家庭保障']),
(5, '复星联合星相守2号长期医疗险（转保版）', '复星联合优选二号长期住院医疗保险（费率可调）（互联网）', 'medical', '复星联合健康保险', 'https://files.huizecdn.com/file3/M00/AC/B9/rBYA3GlFEUWAWcX8AAO1o6m75Qg526.png', '免赔额灵活可选，保证续保20年特需，外购药不限清单。', 180.00, 4409.00, '1-70周岁（1-4类职业）', ARRAY['转保场景','0免赔','特需医疗']),
(6, '众安尊享e生百万医疗险2026版', '众安尊享e生百万医疗保险2026版', 'medical', '众安保险', 'https://files.huizecdn.com/file3/M00/B0/02/rBYA3GlTLeGAGS9sAAEwUtrU9VE280.png', '百万医疗险产品，覆盖住院、特殊门诊等医疗责任。', 255.00, 1420.00, '30天-70周岁（1-6类职业）', ARRAY['百万医疗','医疗保障','责任免除清晰']),
(7, '中英人寿福满佳C款（悦享版）', '中英人寿福满佳C款（悦享版）终身寿险（分红型）', 'life', '中英人寿', 'https://files.huizecdn.com/file3/M00/C1/9A/rBYA3GmJR8qAMR8dAAEJXoRqbAU476.png', '成长型分红险，更高预期收益。', 10000.00, NULL, '30天-57周岁（1-6类职业）', ARRAY['终身寿险','分红型','长期保障']),
(8, '太保福有余2025', '太平洋福有余2025终身寿险（分红型）', 'life', '太平洋人寿', 'https://files.huizecdn.com/file3/M00/AA/6B/rBYA3Gk34AKAZAQCAAEf3uIE2EQ251.png', '终身寿险分红型产品。', 5000.00, NULL, '5天-68周岁（1-6类职业）', ARRAY['终身寿险','分红型']),
(9, '新华人寿E增福优享版', '新华人寿E增福优享版终身寿险（互联网）', 'life', '新华人寿', 'https://files.huizecdn.com/file3/M00/8E/92/rBYA3GitLDaAPo2fAADxu5ximjs300.png', '互联网终身寿险产品。', 10000.00, NULL, '0-70周岁（1-6类职业）', ARRAY['终身寿险','互联网产品']),
(10, '太平洋小蜜蜂6号综合意外险', '太平洋小蜜蜂6号综合意外伤害保险', 'accident', '太平洋财险', 'https://files.huizecdn.com/file3/M00/97/98/rBYA3GjUtNOASrCtAAP85DM8wvE838.png', '综合意外险，含意外伤害及可选附加医疗、猝死责任。', 136.00, 298.00, '18-50周岁（1-3类职业）', ARRAY['综合意外','意外医疗','猝死附加']),
(11, '太平洋小蜜蜂6号玫瑰版综合意外险', '太平洋小蜜蜂6号综合意外伤害保险', 'accident', '太平洋财险', 'https://files.huizecdn.com/file3/M00/97/9A/rBYA3GjUuyyAHuBnAAQ7pqK0eTo763.png', '女性场景综合意外险，与标准版共享基础条款。', 169.00, 439.00, '18-50周岁（1-3类职业）', ARRAY['综合意外','女性场景','共享条款']),
(12, '人保小学童2号Pro学平险', '人保小学童2号Pro学生幼儿保险', 'accident', '中国人保财险', 'https://files.huizecdn.com/file3/M00/8A/2C/rBYA3Gia2NCAPoeMAAOJtnYK38s337.png', '学生幼儿综合保障，含意外、住院、重疾等附加责任。', 240.00, 335.00, '3-24周岁', ARRAY['学平险','意外保障','住院医疗','重疾附加'])
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('products', 'id'), 12, true);

INSERT INTO clauses (id, file_name, file_path, clause_type)
VALUES
(1, '信美相互星辰守护B款少儿重疾险条款.pdf', 'data/raw/kb/信美相互星辰守护B款少儿重疾险条款.pdf', 'main_clause'),
(2, '信美相互星辰守护B款少儿重疾险-产品说明书.pdf', 'data/raw/kb/信美相互星辰守护B款少儿重疾险-产品说明书.pdf', 'product_brochure'),
(3, '信美相互星辰守护B款少儿重疾险-重要提示.pdf', 'data/raw/kb/信美相互星辰守护B款少儿重疾险-重要提示.pdf', 'product_brochure'),
(4, '信美相互附加投保人豁免重疾险条款.pdf', 'data/raw/kb/信美相互附加投保人豁免重疾险条款.pdf', 'additional_clause'),
(5, '信美相互附加投保人豁免重疾险-产品说明书.pdf', 'data/raw/kb/信美相互附加投保人豁免重疾险-产品说明书.pdf', 'product_brochure'),
(6, '信美相互附加投保人豁免重疾险-重要提示.pdf', 'data/raw/kb/信美相互附加投保人豁免重疾险-重要提示.pdf', 'product_brochure'),
(7, '复星联合优选K重疾险(达尔文12号)条款.pdf', 'data/raw/kb/复星联合优选K重疾险(达尔文12号)条款.pdf', 'main_clause'),
(8, '复星联合优选K重疾险(达尔文12号)免责说明.pdf', 'data/raw/kb/复星联合优选K重疾险(达尔文12号)免责说明.pdf', 'exclusion'),
(9, '复星联合优选K重疾险(达尔文12号)产品说明书.pdf', 'data/raw/kb/复星联合优选K重疾险(达尔文12号)产品说明书.pdf', 'product_brochure'),
(10, '复星联合附加投保人豁免重疾险B款(达尔文12号)条款.pdf', 'data/raw/kb/复星联合附加投保人豁免重疾险B款(达尔文12号)条款.pdf', 'additional_clause'),
(11, '复星联合附加投保人豁免重疾险B款(达尔文12号)免责说明.pdf', 'data/raw/kb/复星联合附加投保人豁免重疾险B款(达尔文12号)免责说明.pdf', 'exclusion'),
(12, '复星联合附加投保人豁免重疾险B款(达尔文12号)产品说明书.pdf', 'data/raw/kb/复星联合附加投保人豁免重疾险B款(达尔文12号)产品说明书.pdf', 'product_brochure'),
(13, '复星联合医联有盟重疾险条款.pdf', 'data/raw/kb/复星联合医联有盟重疾险条款.pdf', 'main_clause'),
(14, '复星联合医联有盟重疾险免责说明书.pdf', 'data/raw/kb/复星联合医联有盟重疾险免责说明书.pdf', 'exclusion'),
(15, '复星联合医联有盟重疾险产品说明书.pdf', 'data/raw/kb/复星联合医联有盟重疾险产品说明书.pdf', 'product_brochure'),
(16, '复星联合附加医联有盟长期医疗保险条款.pdf', 'data/raw/kb/复星联合附加医联有盟长期医疗保险条款.pdf', 'additional_clause'),
(17, '复星联合优选二号长期住院医疗险(星相守2号)条款.pdf', 'data/raw/kb/复星联合优选二号长期住院医疗险(星相守2号)条款.pdf', 'main_clause'),
(18, '复星联合优选二号长期住院医疗险(星相守2号)免责条款.pdf', 'data/raw/kb/复星联合优选二号长期住院医疗险(星相守2号)免责条款.pdf', 'exclusion'),
(19, '复星联合优选二号长期住院医疗险(星相守2号)产品说明书.pdf', 'data/raw/kb/复星联合优选二号长期住院医疗险(星相守2号)产品说明书.pdf', 'product_brochure'),
(20, '复星联合附加门急诊医疗险(星相守2号)产品说明书.pdf', 'data/raw/kb/复星联合附加门急诊医疗险(星相守2号)产品说明书.pdf', 'product_brochure'),
(21, '复星联合附加门急诊医疗险(星相守2号)免责条款.pdf', 'data/raw/kb/复星联合附加门急诊医疗险(星相守2号)免责条款.pdf', 'exclusion'),
(22, '众安尊享e生百万医疗险2026版条款.pdf', 'data/raw/kb/众安尊享e生百万医疗险2026版条款.pdf', 'main_clause'),
(23, '众安尊享e生百万医疗险2026版责任免除.pdf', 'data/raw/kb/众安尊享e生百万医疗险2026版责任免除.pdf', 'exclusion'),
(24, '中英人寿福满佳C款(悦享版)终身寿险分红型条款.pdf', 'data/raw/kb/中英人寿福满佳C款(悦享版)终身寿险分红型条款.pdf', 'main_clause'),
(25, '中英人寿福满佳C款(悦享版)终身寿险分红型产品说明书.pdf', 'data/raw/kb/中英人寿福满佳C款(悦享版)终身寿险分红型产品说明书.pdf', 'product_brochure'),
(26, '太平洋福有余2025终身寿险分红型条款.pdf', 'data/raw/kb/太平洋福有余2025终身寿险分红型条款.pdf', 'main_clause'),
(27, '太平洋福有余2025终身寿险分红型产品说明书.pdf', 'data/raw/kb/太平洋福有余2025终身寿险分红型产品说明书.pdf', 'product_brochure'),
(28, '新华人寿E增福优享版终身寿险互联网条款.pdf', 'data/raw/kb/新华人寿E增福优享版终身寿险互联网条款.pdf', 'main_clause'),
(29, '新华人寿E增福优享版终身寿险互联网免责条款.pdf', 'data/raw/kb/新华人寿E增福优享版终身寿险互联网免责条款.pdf', 'exclusion'),
(30, '新华人寿E增福优享版终身寿险互联网产品说明书.pdf', 'data/raw/kb/新华人寿E增福优享版终身寿险互联网产品说明书.pdf', 'product_brochure'),
(31, '太平洋小蜜蜂6号综合意外险条款.pdf', 'data/raw/kb/太平洋小蜜蜂6号综合意外险条款.pdf', 'main_clause'),
(32, '太平洋小蜜蜂6号综合意外险猝死附加条款.pdf', 'data/raw/kb/太平洋小蜜蜂6号综合意外险猝死附加条款.pdf', 'additional_clause'),
(33, '太平洋小蜜蜂6号综合意外险医疗附加条款.pdf', 'data/raw/kb/太平洋小蜜蜂6号综合意外险医疗附加条款.pdf', 'additional_clause'),
(34, '人保小学童2号Pro学平险学生幼儿意外伤害条款.pdf', 'data/raw/kb/人保小学童2号Pro学平险学生幼儿意外伤害条款.pdf', 'main_clause'),
(35, '人保小学童2号Pro学平险住院医疗附加条款.pdf', 'data/raw/kb/人保小学童2号Pro学平险住院医疗附加条款.pdf', 'additional_clause'),
(36, '人保小学童2号Pro学平险重大疾病附加条款.pdf', 'data/raw/kb/人保小学童2号Pro学平险重大疾病附加条款.pdf', 'additional_clause'),
(37, '人保小学童2号Pro学平险意外伤害医疗附加条款.pdf', 'data/raw/kb/人保小学童2号Pro学平险意外伤害医疗附加条款.pdf', 'additional_clause'),
(38, '人保小学童2号Pro学平险住院津贴附加条款.pdf', 'data/raw/kb/人保小学童2号Pro学平险住院津贴附加条款.pdf', 'additional_clause'),
(39, '人保小学童2号Pro学平险美容缝合牙齿修复附加条款.pdf', 'data/raw/kb/人保小学童2号Pro学平险美容缝合牙齿修复附加条款.pdf', 'additional_clause')
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('clauses', 'id'), 39, true);

INSERT INTO product_clauses (product_id, clause_id)
VALUES
(1,1),(1,2),(1,3),(1,4),(1,5),(1,6),
(2,7),(2,8),(2,9),(2,10),(2,11),(2,12),
(3,13),(3,14),(3,15),(3,16),
(4,17),(4,18),(4,19),(4,20),(4,21),
(5,17),(5,18),(5,19),(5,20),(5,21),
(6,22),(6,23),
(7,24),(7,25),
(8,26),(8,27),
(9,28),(9,29),(9,30),
(10,31),(10,32),(10,33),
(11,31),(11,32),(11,33),
(12,34),(12,35),(12,36),(12,37),(12,38),(12,39)
ON CONFLICT (product_id, clause_id) DO NOTHING;

INSERT INTO rate_table_files (id, product_id, file_name, file_path, status)
VALUES
('10000000-0000-0000-0000-000000000001', 2, '复星联合优选K重疾险(达尔文12号)费率表.pdf', 'data/raw/rate_tables/复星联合优选K重疾险(达尔文12号)费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000002', 3, '复星联合医联有盟重疾险费率表.pdf', 'data/raw/rate_tables/复星联合医联有盟重疾险费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000003', 4, '复星联合优选二号长期住院医疗险(星相守2号)费率表.pdf', 'data/raw/rate_tables/复星联合优选二号长期住院医疗险(星相守2号)费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000004', 6, '众安尊享e生百万医疗险2026版费率表.pdf', 'data/raw/rate_tables/众安尊享e生百万医疗险2026版费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000005', 10, '太平洋小蜜蜂6号综合意外险费率表.pdf', 'data/raw/rate_tables/太平洋小蜜蜂6号综合意外险费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000006', 11, '太平洋小蜜蜂6号玫瑰版综合意外险费率表.pdf', 'data/raw/rate_tables/太平洋小蜜蜂6号玫瑰版综合意外险费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000007', 12, '人保小学童2号Pro学平险费率表.pdf', 'data/raw/rate_tables/人保小学童2号Pro学平险费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000008', 7, '中英人寿福满佳C款(悦享版)终身寿险分红型费率表.pdf', 'data/raw/rate_tables/中英人寿福满佳C款(悦享版)终身寿险分红型费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000009', 8, '太平洋福有余2025终身寿险分红型费率表.pdf', 'data/raw/rate_tables/太平洋福有余2025终身寿险分红型费率表.pdf', 'pending'),
('10000000-0000-0000-0000-000000000010', 9, '新华人寿E增福优享版终身寿险互联网费率表.pdf', 'data/raw/rate_tables/新华人寿E增福优享版终身寿险互联网费率表.pdf', 'pending')
ON CONFLICT (id) DO NOTHING;

-- ==== V4__order_idempotency_and_demo_user.sql ====
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS idempotency_fingerprint VARCHAR(64);

-- 演示账号：demo / demo123（bcrypt 哈希）
INSERT INTO users (id, username, email, password_hash, display_name, status)
VALUES (
    1,
    'demo',
    'demo@example.com',
    '$2b$12$5yfP9N.Baf.Z37Mmt5za7Ooz/TL1cXRjEEMSECbSbtTzJx5tagacu',
    '演示用户',
    'active'
)
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('users', 'id'), 1, true);


-- ==== V5__seed_structured_rate_tables.sql ====
UPDATE rate_table_files
SET status = 'active',
    parser_version = COALESCE(parser_version, 'manual_seed_v1'),
    activated_at = COALESCE(activated_at, CURRENT_TIMESTAMP)
WHERE id IN (
    '10000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000004',
    '10000000-0000-0000-0000-000000000005'
);

INSERT INTO rate_plans (
    id, product_id, plan_code, plan_name, rate_type,
    required_params, optional_params, status
)
VALUES
('20000000-0000-0000-0000-000000000001', 2, 'standard', '标准责任', 'per_10000_sum_assured',
 '["age","gender","coverage_amount","payment_period","coverage_period"]'::jsonb,
 '["occupation_class","social_security"]'::jsonb, 'active'),
('20000000-0000-0000-0000-000000000002', 6, 'standard', '标准计划', 'age_band_plan_premium',
 '["age","social_security","deductible"]'::jsonb,
 '["gender","occupation_class"]'::jsonb, 'active'),
('20000000-0000-0000-0000-000000000003', 10, 'standard', '标准计划', 'fixed_plan_premium',
 '["coverage_amount","occupation_class"]'::jsonb,
 '["age","gender"]'::jsonb, 'active')
ON CONFLICT (product_id, plan_code) DO UPDATE
SET plan_name = EXCLUDED.plan_name,
    rate_type = EXCLUDED.rate_type,
    required_params = EXCLUDED.required_params,
    optional_params = EXCLUDED.optional_params,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO rate_table_items (
    id, rate_file_id, product_id, plan_code, rate_type,
    age_min, age_max, gender, occupation_class, social_security,
    payment_period, coverage_period, coverage_amount, deductible,
    dimensions, rate_value, premium, source_page, source_table, status
)
VALUES
('30000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000001', 2, 'standard', 'per_10000_sum_assured',
 30, 30, 'female', 'all', 'all',
 '20y', 'lifetime', NULL, NULL,
 '{"note":"manual sample from structured rate table pipeline"}'::jsonb, 78.000000, NULL, 3, '女性30岁20年交终身费率样例', 'active'),
('30000000-0000-0000-0000-000000000002',
 '10000000-0000-0000-0000-000000000001', 2, 'standard', 'per_10000_sum_assured',
 30, 30, 'male', 'all', 'all',
 '20y', 'lifetime', NULL, NULL,
 '{"note":"manual sample from structured rate table pipeline"}'::jsonb, 86.000000, NULL, 3, '男性30岁20年交终身费率样例', 'active'),
('30000000-0000-0000-0000-000000000003',
 '10000000-0000-0000-0000-000000000004', 6, 'standard', 'age_band_plan_premium',
 0, 30, 'all', 'all', 'yes',
 'annual', '1y', 1000000.00, 10000.00,
 '{"note":"manual sample from structured rate table pipeline"}'::jsonb, NULL, 350.00, 2, '有社保1万免赔0-30岁样例', 'active'),
('30000000-0000-0000-0000-000000000004',
 '10000000-0000-0000-0000-000000000004', 6, 'standard', 'age_band_plan_premium',
 31, 50, 'all', 'all', 'yes',
 'annual', '1y', 1000000.00, 10000.00,
 '{"note":"manual sample from structured rate table pipeline"}'::jsonb, NULL, 600.00, 2, '有社保1万免赔31-50岁样例', 'active'),
('30000000-0000-0000-0000-000000000005',
 '10000000-0000-0000-0000-000000000004', 6, 'standard', 'age_band_plan_premium',
 51, 70, 'all', 'all', 'yes',
 'annual', '1y', 1000000.00, 10000.00,
 '{"note":"manual sample from structured rate table pipeline"}'::jsonb, NULL, 1200.00, 2, '有社保1万免赔51-70岁样例', 'active'),
('30000000-0000-0000-0000-000000000006',
 '10000000-0000-0000-0000-000000000005', 10, 'standard', 'fixed_plan_premium',
 NULL, NULL, 'all', '1', 'all',
 'annual', NULL, 500000.00, NULL,
 '{"note":"manual sample from structured rate table pipeline"}'::jsonb, NULL, 136.00, 1, '综合意外标准计划样例', 'active')
ON CONFLICT (id) DO NOTHING;

-- ==== V6__pricing_schema_mock_adapter.sql ====
CREATE TABLE IF NOT EXISTS product_pricing_schemas (
    id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    scenario VARCHAR(80) NOT NULL DEFAULT 'premium_by_coverage',
    schema_version VARCHAR(80) NOT NULL,
    schema_json JSONB NOT NULL,
    schema_hash VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    CONSTRAINT uk_product_pricing_schema_version UNIQUE (product_id, scenario, schema_version),
    CONSTRAINT chk_product_pricing_schemas_status CHECK (status IN ('draft', 'active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS insurer_api_adapters (
    id UUID PRIMARY KEY,
    insurer_code VARCHAR(80) NOT NULL UNIQUE,
    adapter_type VARCHAR(40) NOT NULL,
    adapter_name VARCHAR(120) NOT NULL,
    base_url VARCHAR(500),
    auth_type VARCHAR(40) NOT NULL DEFAULT 'none',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_insurer_api_adapters_type CHECK (adapter_type IN ('mock', 'http')),
    CONSTRAINT chk_insurer_api_adapters_status CHECK (status IN ('active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS product_pricing_bindings (
    id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    pricing_schema_id UUID NOT NULL REFERENCES product_pricing_schemas(id),
    adapter_id UUID NOT NULL REFERENCES insurer_api_adapters(id),
    external_product_code VARCHAR(120) NOT NULL,
    api_code VARCHAR(120) NOT NULL,
    field_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
    mock_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_product_pricing_bindings_status CHECK (status IN ('active', 'inactive'))
);

ALTER TABLE premium_quotes
    ADD COLUMN IF NOT EXISTS pricing_schema_id UUID REFERENCES product_pricing_schemas(id),
    ADD COLUMN IF NOT EXISTS schema_version VARCHAR(80),
    ADD COLUMN IF NOT EXISTS adapter_id UUID REFERENCES insurer_api_adapters(id),
    ADD COLUMN IF NOT EXISTS answers JSONB,
    ADD COLUMN IF NOT EXISTS external_request JSONB,
    ADD COLUMN IF NOT EXISTS external_response JSONB;

ALTER TABLE premium_quotes DROP CONSTRAINT IF EXISTS chk_premium_quotes_pricing_mode;

ALTER TABLE premium_quotes
    ADD CONSTRAINT chk_premium_quotes_pricing_mode CHECK (
        pricing_mode IN ('table', 'demo_formula', 'mock_adapter', 'insurer_api', 'local_fallback')
    );

CREATE INDEX IF NOT EXISTS idx_product_pricing_schemas_product
    ON product_pricing_schemas(product_id, scenario, status);

CREATE INDEX IF NOT EXISTS idx_product_pricing_bindings_product
    ON product_pricing_bindings(product_id, status);

INSERT INTO insurer_api_adapters (
    id, insurer_code, adapter_type, adapter_name, config, status
)
VALUES
('41000000-0000-0000-0000-000000000001', 'mock_fosun', 'mock', '复星联合 mock 试算适配器', '{}'::jsonb, 'active'),
('41000000-0000-0000-0000-000000000002', 'mock_zhongan', 'mock', '众安保险 mock 试算适配器', '{}'::jsonb, 'active'),
('41000000-0000-0000-0000-000000000003', 'mock_cpci', 'mock', '太平洋财险 mock 试算适配器', '{}'::jsonb, 'active')
ON CONFLICT (insurer_code) DO UPDATE
SET adapter_type = EXCLUDED.adapter_type,
    adapter_name = EXCLUDED.adapter_name,
    config = EXCLUDED.config,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO product_pricing_schemas (
    id, product_id, scenario, schema_version, schema_json, schema_hash, status, activated_at
)
VALUES
('40000000-0000-0000-0000-000000000001', 2, 'premium_by_coverage', '2026-06-09.v1',
 '{
   "title": "达尔文12号重大疾病保险试算",
   "fields": [
     {"key": "plan_code", "label": "保障计划", "type": "plan_select", "required": true, "options_ref": "plan_options"},
     {"key": "insured.age", "label": "被保人年龄", "type": "integer", "required": true, "min": 0, "max": 35},
     {"key": "insured.gender", "label": "被保人性别", "type": "select", "required": true, "options": [{"value": "male", "label": "男"}, {"value": "female", "label": "女"}]},
     {"key": "coverage.coverage_amount", "label": "基本保险金额", "type": "money", "required": true, "options": [300000, 500000, 1000000]},
     {"key": "coverage.payment_period", "label": "缴费年限", "type": "select", "required": true, "options": [{"value": "10y", "label": "10年"}, {"value": "20y", "label": "20年"}, {"value": "30y", "label": "30年"}]},
     {"key": "coverage.coverage_period", "label": "保障期限", "type": "select", "required": true, "options": [{"value": "lifetime", "label": "终身"}]}
   ],
   "plan_options": [
     {"value": "basic", "label": "基础责任"},
     {"value": "classic", "label": "经典责任"},
     {"value": "premium", "label": "尊享责任"}
   ],
   "rules": []
 }'::jsonb, NULL, 'active', CURRENT_TIMESTAMP),
('40000000-0000-0000-0000-000000000002', 6, 'premium_by_coverage', '2026-06-09.v1',
 '{
   "title": "众安尊享e生百万医疗险2026版试算",
   "fields": [
     {"key": "plan_code", "label": "保障计划", "type": "plan_select", "required": true, "options_ref": "plan_options"},
     {"key": "insured.age", "label": "被保人年龄", "type": "integer", "required": true, "min": 0, "max": 70},
     {"key": "insured.social_security", "label": "是否有社保", "type": "select", "required": true, "options": [{"value": "yes", "label": "有"}, {"value": "no", "label": "无"}]},
     {"key": "coverage.deductible", "label": "免赔额", "type": "money", "required": true, "options": [0, 10000]},
     {"key": "coverage.coverage_amount", "label": "一般医疗保额", "type": "money", "required": true, "options": [1000000, 2000000]}
   ],
   "plan_options": [
     {"value": "standard", "label": "标准版"},
     {"value": "plus", "label": "升级版"}
   ],
   "rules": []
 }'::jsonb, NULL, 'active', CURRENT_TIMESTAMP),
('40000000-0000-0000-0000-000000000003', 10, 'premium_by_coverage', '2026-06-09.v1',
 '{
   "title": "太平洋小蜜蜂6号综合意外险试算",
   "fields": [
     {"key": "plan_code", "label": "保障计划", "type": "plan_select", "required": true, "options_ref": "plan_options"},
     {"key": "insured.age", "label": "被保人年龄", "type": "integer", "required": true, "min": 18, "max": 65},
     {"key": "insured.occupation_class", "label": "承保职业", "type": "select", "required": true, "options": [{"value": "1-4", "label": "1-4类"}, {"value": "5-6", "label": "5-6类"}]},
     {"key": "coverage.coverage_amount", "label": "意外身故/伤残保额", "type": "money", "required": true, "options": [300000, 500000, 1000000]}
   ],
   "plan_options": [
     {"value": "basic", "label": "基础版", "description": "低保费基础保障"},
     {"value": "classic", "label": "经典版", "description": "均衡保障"},
     {"value": "premium", "label": "尊享版", "description": "高额保障"}
   ],
   "rules": []
 }'::jsonb, NULL, 'active', CURRENT_TIMESTAMP)
ON CONFLICT (product_id, scenario, schema_version) DO UPDATE
SET schema_json = EXCLUDED.schema_json,
    schema_hash = EXCLUDED.schema_hash,
    status = EXCLUDED.status,
    activated_at = EXCLUDED.activated_at;

INSERT INTO product_pricing_bindings (
    id, product_id, pricing_schema_id, adapter_id,
    external_product_code, api_code, field_mapping, response_mapping, mock_config, status
)
VALUES
('42000000-0000-0000-0000-000000000001', 2, '40000000-0000-0000-0000-000000000001', '41000000-0000-0000-0000-000000000001',
 'FOSUN_DW12', 'mock_premium_trial_v1',
 '{"plan_code":"packageCode","insured.age":"age","insured.gender":"gender","coverage.coverage_amount":"sumInsured","coverage.payment_period":"paymentPeriod","coverage.coverage_period":"coveragePeriod"}'::jsonb,
 '{}'::jsonb,
 '{"base_premium_by_plan":{"basic":500,"classic":700,"premium":950},"age_factor":[{"min":0,"max":17,"factor":0.8},{"min":18,"max":35,"factor":1.0}],"gender_factor":{"male":1.1,"female":1.0},"coverage_unit":500000,"coverage_factor_enabled":true}'::jsonb,
 'active'),
('42000000-0000-0000-0000-000000000002', 6, '40000000-0000-0000-0000-000000000002', '41000000-0000-0000-0000-000000000002',
 'ZA_ZXES_2026', 'mock_premium_trial_v1',
 '{"plan_code":"packageCode","insured.age":"age","insured.social_security":"hasSocialSecurity","coverage.deductible":"deductible","coverage.coverage_amount":"sumInsured"}'::jsonb,
 '{}'::jsonb,
 '{"base_premium_by_plan":{"standard":300,"plus":460},"age_factor":[{"min":0,"max":30,"factor":1.0},{"min":31,"max":50,"factor":1.6},{"min":51,"max":70,"factor":3.0}],"social_security_factor":{"yes":1.0,"no":1.3},"deductible_factor":{"0":1.5,"10000":1.0},"coverage_unit":1000000,"coverage_factor_enabled":true}'::jsonb,
 'active'),
('42000000-0000-0000-0000-000000000003', 10, '40000000-0000-0000-0000-000000000003', '41000000-0000-0000-0000-000000000003',
 'CPCI_XMF6', 'mock_premium_trial_v1',
 '{"plan_code":"packageCode","insured.age":"age","insured.occupation_class":"occupationClass","coverage.coverage_amount":"sumInsured"}'::jsonb,
 '{}'::jsonb,
 '{"base_premium_by_plan":{"basic":120,"classic":180,"premium":260},"age_factor":[{"min":18,"max":45,"factor":1.0},{"min":46,"max":65,"factor":1.4}],"occupation_factor":{"1-4":1.0,"5-6":1.8},"coverage_unit":500000,"coverage_factor_enabled":true}'::jsonb,
 'active')
ON CONFLICT (id) DO UPDATE
SET pricing_schema_id = EXCLUDED.pricing_schema_id,
    adapter_id = EXCLUDED.adapter_id,
    external_product_code = EXCLUDED.external_product_code,
    api_code = EXCLUDED.api_code,
    field_mapping = EXCLUDED.field_mapping,
    response_mapping = EXCLUDED.response_mapping,
    mock_config = EXCLUDED.mock_config,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

-- ==== V7__insurance_plans_application_journeys.sql ====
CREATE TABLE IF NOT EXISTS customer_insurance_plans (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    thread_id UUID,
    plan_name VARCHAR(120) NOT NULL,
    insured_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    estimated_premium_min DECIMAL(14,2),
    estimated_premium_max DECIMAL(14,2),
    estimated_annual_premium DECIMAL(14,2),
    confirmed_annual_premium DECIMAL(14,2),
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_customer_insurance_plans_status CHECK (status IN ('draft', 'active', 'archived'))
);

CREATE TABLE IF NOT EXISTS customer_insurance_plan_items (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES customer_insurance_plans(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    category VARCHAR(50) NOT NULL,
    priority INT NOT NULL DEFAULT 1,
    recommendation_reason TEXT,
    suggested_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    price_mode VARCHAR(20) NOT NULL DEFAULT 'range',
    estimated_premium_min DECIMAL(14,2),
    estimated_premium_max DECIMAL(14,2),
    estimated_annual_premium DECIMAL(14,2),
    quote_id UUID REFERENCES premium_quotes(id),
    confirmed_annual_premium DECIMAL(14,2),
    application_journey_id UUID,
    status VARCHAR(30) NOT NULL DEFAULT 'recommended',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_plan_items_category CHECK (category IN ('medical', 'critical_illness', 'accident', 'life')),
    CONSTRAINT chk_plan_items_price_mode CHECK (price_mode IN ('range', 'estimated', 'quoted')),
    CONSTRAINT chk_plan_items_status CHECK (status IN ('recommended', 'estimated', 'quoted', 'applying', 'insured', 'skipped'))
);

CREATE TABLE IF NOT EXISTS application_journeys (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    plan_id UUID REFERENCES customer_insurance_plans(id),
    plan_item_id UUID REFERENCES customer_insurance_plan_items(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quote_id UUID REFERENCES premium_quotes(id),
    current_step VARCHAR(50) NOT NULL DEFAULT 'pricing',
    status VARCHAR(30) NOT NULL DEFAULT 'in_progress',
    notice_acknowledged_at TIMESTAMP,
    health_disclosure_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    underwriting_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    application_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    order_id UUID REFERENCES orders(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_application_journeys_step CHECK (current_step IN (
        'pricing', 'notice', 'health_disclosure', 'underwriting', 'application_info', 'submit', 'payment'
    )),
    CONSTRAINT chk_application_journeys_status CHECK (status IN (
        'in_progress', 'blocked', 'submitted', 'payment_pending', 'paid', 'cancelled'
    ))
);

CREATE INDEX IF NOT EXISTS idx_customer_insurance_plans_user
    ON customer_insurance_plans(user_id, status);

CREATE INDEX IF NOT EXISTS idx_customer_insurance_plan_items_plan
    ON customer_insurance_plan_items(plan_id, status);

CREATE INDEX IF NOT EXISTS idx_application_journeys_user
    ON application_journeys(user_id, status);

CREATE INDEX IF NOT EXISTS idx_application_journeys_plan_item
    ON application_journeys(plan_item_id);

-- ==== V8__simplify_insurance_plan_status.sql ====
DROP TABLE IF EXISTS application_journeys;

ALTER TABLE customer_insurance_plan_items
    DROP COLUMN IF EXISTS application_journey_id;

ALTER TABLE customer_insurance_plan_items
    DROP CONSTRAINT IF EXISTS chk_plan_items_status;

UPDATE customer_insurance_plan_items
SET status = CASE WHEN status = 'insured' THEN 'insured' ELSE 'uninsured' END;

ALTER TABLE customer_insurance_plan_items
    ALTER COLUMN status SET DEFAULT 'uninsured';

ALTER TABLE customer_insurance_plan_items
    ADD CONSTRAINT chk_plan_items_status
        CHECK (status IN ('uninsured', 'insured'));

ALTER TABLE customer_insurance_plans
    DROP CONSTRAINT IF EXISTS chk_customer_insurance_plans_status;

UPDATE customer_insurance_plans plan
SET status = CASE
    WHEN NOT EXISTS (
        SELECT 1 FROM customer_insurance_plan_items item WHERE item.plan_id = plan.id
    ) THEN 'uninsured'
    WHEN NOT EXISTS (
        SELECT 1 FROM customer_insurance_plan_items item
        WHERE item.plan_id = plan.id AND item.status = 'uninsured'
    ) THEN 'insured'
    WHEN EXISTS (
        SELECT 1 FROM customer_insurance_plan_items item
        WHERE item.plan_id = plan.id AND item.status = 'insured'
    ) THEN 'applying'
    ELSE 'uninsured'
END;

ALTER TABLE customer_insurance_plans
    ALTER COLUMN status SET DEFAULT 'uninsured';

ALTER TABLE customer_insurance_plans
    ADD CONSTRAINT chk_customer_insurance_plans_status
        CHECK (status IN ('uninsured', 'applying', 'insured'));

-- ==== V9__remove_plan_estimated_premium_max.sql ====
ALTER TABLE customer_insurance_plan_items
    DROP COLUMN IF EXISTS estimated_premium_max;

ALTER TABLE customer_insurance_plans
    DROP COLUMN IF EXISTS estimated_premium_max;

-- ==== V10__remove_unused_plan_item_fields.sql ====
ALTER TABLE customer_insurance_plan_items
    DROP CONSTRAINT IF EXISTS chk_plan_items_price_mode;

ALTER TABLE customer_insurance_plan_items
    DROP COLUMN IF EXISTS suggested_coverage,
    DROP COLUMN IF EXISTS price_mode;

-- ==== V11__simplify_plan_budget_and_details.sql ====
ALTER TABLE customer_insurance_plans
    ADD COLUMN summary TEXT,
    ADD COLUMN budget_note TEXT;

ALTER TABLE customer_insurance_plans
    RENAME COLUMN estimated_premium_min TO annual_premium_budget;

ALTER TABLE customer_insurance_plans
    DROP COLUMN IF EXISTS estimated_annual_premium,
    DROP COLUMN IF EXISTS confirmed_annual_premium;

ALTER TABLE customer_insurance_plan_items
    RENAME COLUMN estimated_premium_min TO annual_premium_budget;

ALTER TABLE customer_insurance_plan_items
    DROP COLUMN IF EXISTS estimated_annual_premium,
    DROP COLUMN IF EXISTS confirmed_annual_premium,
    DROP COLUMN IF EXISTS quote_id;

-- ==== V12__policies_and_claim_tracking.sql ====
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    policy_number VARCHAR(60) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    effective_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_policies_status
        CHECK (status IN ('pending', 'active', 'expired', 'terminated'))
);

ALTER TABLE claims
    ADD COLUMN IF NOT EXISTS policy_id UUID REFERENCES policies(id),
    ADD COLUMN IF NOT EXISTS claim_number VARCHAR(60);

CREATE UNIQUE INDEX IF NOT EXISTS uk_claims_claim_number
    ON claims(claim_number)
    WHERE claim_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_policies_user_status_effective
    ON policies(user_id, status, effective_at DESC);

CREATE INDEX IF NOT EXISTS idx_claims_user_policy_updated
    ON claims(user_id, policy_id, updated_at DESC);

INSERT INTO policies (
    id, user_id, product_id, policy_number, status, effective_at, expires_at
)
VALUES
(
    '10000000-0000-0000-0000-000000000001',
    1,
    6,
    'POL-DEMO-2026-0001',
    'active',
    CURRENT_TIMESTAMP - INTERVAL '120 days',
    CURRENT_TIMESTAMP + INTERVAL '245 days'
),
(
    '10000000-0000-0000-0000-000000000002',
    1,
    10,
    'POL-DEMO-2024-0002',
    'expired',
    CURRENT_TIMESTAMP - INTERVAL '730 days',
    CURRENT_TIMESTAMP - INTERVAL '365 days'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO claims (
    id, user_id, policy_id, product_id, claim_number, claim_type,
    amount, description, status, submitted_at, updated_at
)
VALUES
(
    '20000000-0000-0000-0000-000000000001',
    1,
    '10000000-0000-0000-0000-000000000001',
    6,
    'CLM-DEMO-2026-0001',
    'medical',
    NULL,
    '住院医疗费用理赔材料审核中',
    'reviewing',
    CURRENT_TIMESTAMP - INTERVAL '5 days',
    CURRENT_TIMESTAMP - INTERVAL '1 day'
),
(
    '20000000-0000-0000-0000-000000000002',
    1,
    '10000000-0000-0000-0000-000000000002',
    10,
    'CLM-DEMO-2025-0002',
    'accident',
    1200.00,
    '意外医疗理赔已完成赔付',
    'paid',
    CURRENT_TIMESTAMP - INTERVAL '400 days',
    CURRENT_TIMESTAMP - INTERVAL '390 days'
)
ON CONFLICT (id) DO NOTHING;

-- ==== V13__remove_plan_thread_and_add_comments.sql ====
ALTER TABLE customer_insurance_plans
    DROP COLUMN IF EXISTS thread_id;

COMMENT ON TABLE app_metadata IS '业务服务的数据库元数据与初始化标记';
COMMENT ON COLUMN app_metadata.key IS '元数据键';
COMMENT ON COLUMN app_metadata.value IS '元数据值';
COMMENT ON COLUMN app_metadata.created_at IS '创建时间';

COMMENT ON TABLE users IS '保险商城用户账户';
COMMENT ON COLUMN users.id IS '用户主键';
COMMENT ON COLUMN users.username IS '登录用户名';
COMMENT ON COLUMN users.email IS '用户邮箱';
COMMENT ON COLUMN users.password_hash IS '加密后的登录密码';
COMMENT ON COLUMN users.display_name IS '用户展示名称';
COMMENT ON COLUMN users.status IS '账户状态';
COMMENT ON COLUMN users.created_at IS '创建时间';
COMMENT ON COLUMN users.updated_at IS '最后更新时间';

COMMENT ON TABLE products IS '保险商城在售及历史保险产品';
COMMENT ON COLUMN products.id IS '产品主键';
COMMENT ON COLUMN products.name IS '商城展示名称';
COMMENT ON COLUMN products.clause_name IS '保险条款中的正式产品名称';
COMMENT ON COLUMN products.category IS '险种分类：医疗、重疾、意外或寿险';
COMMENT ON COLUMN products.insurer IS '承保保险公司';
COMMENT ON COLUMN products.image_url IS '产品展示图片地址';
COMMENT ON COLUMN products.description IS '产品简介';
COMMENT ON COLUMN products.min_premium IS '产品公开的最低年缴保费参考';
COMMENT ON COLUMN products.max_premium IS '产品公开的最高保费参考，可为空';
COMMENT ON COLUMN products.target_group IS '适用人群说明';
COMMENT ON COLUMN products.highlights IS '产品亮点列表';
COMMENT ON COLUMN products.status IS '产品状态';
COMMENT ON COLUMN products.created_at IS '创建时间';
COMMENT ON COLUMN products.updated_at IS '最后更新时间';

COMMENT ON TABLE clauses IS '保险条款及产品资料文件元数据';
COMMENT ON COLUMN clauses.id IS '条款主键';
COMMENT ON COLUMN clauses.file_name IS '条款文件名';
COMMENT ON COLUMN clauses.file_path IS '条款文件相对路径';
COMMENT ON COLUMN clauses.clause_type IS '条款文件类型';
COMMENT ON COLUMN clauses.created_at IS '创建时间';
COMMENT ON COLUMN clauses.updated_at IS '最后更新时间';

COMMENT ON TABLE product_clauses IS '保险产品与条款文件的多对多关联';
COMMENT ON COLUMN product_clauses.id IS '关联记录主键';
COMMENT ON COLUMN product_clauses.product_id IS '产品主键';
COMMENT ON COLUMN product_clauses.clause_id IS '条款主键';
COMMENT ON COLUMN product_clauses.created_at IS '创建时间';

COMMENT ON TABLE rate_table_files IS '从保险公司费率文件抽取的文件级记录';
COMMENT ON COLUMN rate_table_files.id IS '费率文件主键';
COMMENT ON COLUMN rate_table_files.product_id IS '所属产品';
COMMENT ON COLUMN rate_table_files.file_name IS '费率文件名';
COMMENT ON COLUMN rate_table_files.file_path IS '费率文件路径';
COMMENT ON COLUMN rate_table_files.file_hash IS '文件内容哈希';
COMMENT ON COLUMN rate_table_files.parser_version IS '解析器版本';
COMMENT ON COLUMN rate_table_files.status IS '解析和校验状态';
COMMENT ON COLUMN rate_table_files.validation_report IS '结构化校验报告';
COMMENT ON COLUMN rate_table_files.created_at IS '创建时间';
COMMENT ON COLUMN rate_table_files.activated_at IS '启用时间';

COMMENT ON TABLE rate_plans IS '产品费率计划及试算参数定义';
COMMENT ON COLUMN rate_plans.id IS '费率计划主键';
COMMENT ON COLUMN rate_plans.product_id IS '所属产品';
COMMENT ON COLUMN rate_plans.plan_code IS '产品内唯一的计划编码';
COMMENT ON COLUMN rate_plans.plan_name IS '计划展示名称';
COMMENT ON COLUMN rate_plans.rate_type IS '费率计算类型';
COMMENT ON COLUMN rate_plans.currency IS '保费币种';
COMMENT ON COLUMN rate_plans.required_params IS '必填试算参数定义';
COMMENT ON COLUMN rate_plans.optional_params IS '可选试算参数定义';
COMMENT ON COLUMN rate_plans.status IS '计划状态';
COMMENT ON COLUMN rate_plans.created_at IS '创建时间';
COMMENT ON COLUMN rate_plans.updated_at IS '最后更新时间';

COMMENT ON TABLE rate_table_items IS '费率表中的结构化费率明细';
COMMENT ON COLUMN rate_table_items.id IS '费率明细主键';
COMMENT ON COLUMN rate_table_items.rate_file_id IS '来源费率文件';
COMMENT ON COLUMN rate_table_items.product_id IS '所属产品';
COMMENT ON COLUMN rate_table_items.plan_code IS '费率计划编码';
COMMENT ON COLUMN rate_table_items.rate_type IS '费率计算类型';
COMMENT ON COLUMN rate_table_items.age_min IS '适用最小年龄';
COMMENT ON COLUMN rate_table_items.age_max IS '适用最大年龄';
COMMENT ON COLUMN rate_table_items.gender IS '适用性别';
COMMENT ON COLUMN rate_table_items.occupation_class IS '适用职业类别';
COMMENT ON COLUMN rate_table_items.social_security IS '社保条件';
COMMENT ON COLUMN rate_table_items.payment_period IS '缴费期限';
COMMENT ON COLUMN rate_table_items.coverage_period IS '保障期限';
COMMENT ON COLUMN rate_table_items.coverage_amount IS '保险金额';
COMMENT ON COLUMN rate_table_items.deductible IS '免赔额';
COMMENT ON COLUMN rate_table_items.dimensions IS '其他费率维度';
COMMENT ON COLUMN rate_table_items.rate_value IS '费率值';
COMMENT ON COLUMN rate_table_items.premium IS '固定保费值';
COMMENT ON COLUMN rate_table_items.source_page IS '来源页码';
COMMENT ON COLUMN rate_table_items.source_table IS '来源表格名称';
COMMENT ON COLUMN rate_table_items.status IS '费率明细状态';
COMMENT ON COLUMN rate_table_items.created_at IS '创建时间';

COMMENT ON TABLE product_pricing_schemas IS '产品动态保费试算表单定义';
COMMENT ON COLUMN product_pricing_schemas.id IS '试算模板主键';
COMMENT ON COLUMN product_pricing_schemas.product_id IS '所属产品';
COMMENT ON COLUMN product_pricing_schemas.scenario IS '试算业务场景';
COMMENT ON COLUMN product_pricing_schemas.schema_version IS '模板版本';
COMMENT ON COLUMN product_pricing_schemas.schema_json IS '前端动态表单 JSON Schema';
COMMENT ON COLUMN product_pricing_schemas.schema_hash IS '模板内容哈希';
COMMENT ON COLUMN product_pricing_schemas.status IS '模板状态';
COMMENT ON COLUMN product_pricing_schemas.created_at IS '创建时间';
COMMENT ON COLUMN product_pricing_schemas.activated_at IS '启用时间';

COMMENT ON TABLE insurer_api_adapters IS '保险公司保费试算接口适配器配置';
COMMENT ON COLUMN insurer_api_adapters.id IS '适配器主键';
COMMENT ON COLUMN insurer_api_adapters.insurer_code IS '保险公司适配器编码';
COMMENT ON COLUMN insurer_api_adapters.adapter_type IS '适配器类型：mock 或 HTTP';
COMMENT ON COLUMN insurer_api_adapters.adapter_name IS '适配器名称';
COMMENT ON COLUMN insurer_api_adapters.base_url IS '保险公司接口基础地址';
COMMENT ON COLUMN insurer_api_adapters.auth_type IS '接口认证方式';
COMMENT ON COLUMN insurer_api_adapters.config IS '适配器非敏感配置';
COMMENT ON COLUMN insurer_api_adapters.status IS '适配器状态';
COMMENT ON COLUMN insurer_api_adapters.created_at IS '创建时间';
COMMENT ON COLUMN insurer_api_adapters.updated_at IS '最后更新时间';

COMMENT ON TABLE product_pricing_bindings IS '产品、试算模板与保险公司适配器的绑定';
COMMENT ON COLUMN product_pricing_bindings.id IS '绑定主键';
COMMENT ON COLUMN product_pricing_bindings.product_id IS '所属产品';
COMMENT ON COLUMN product_pricing_bindings.pricing_schema_id IS '试算模板主键';
COMMENT ON COLUMN product_pricing_bindings.adapter_id IS '适配器主键';
COMMENT ON COLUMN product_pricing_bindings.external_product_code IS '保险公司外部产品编码';
COMMENT ON COLUMN product_pricing_bindings.api_code IS '保险公司接口编码';
COMMENT ON COLUMN product_pricing_bindings.field_mapping IS '内部字段到外部字段的映射';
COMMENT ON COLUMN product_pricing_bindings.response_mapping IS '外部响应到统一响应的映射';
COMMENT ON COLUMN product_pricing_bindings.mock_config IS '教学 Mock 试算配置';
COMMENT ON COLUMN product_pricing_bindings.status IS '绑定状态';
COMMENT ON COLUMN product_pricing_bindings.created_at IS '创建时间';
COMMENT ON COLUMN product_pricing_bindings.updated_at IS '最后更新时间';

COMMENT ON TABLE premium_quotes IS '单产品保费试算结果';
COMMENT ON COLUMN premium_quotes.id IS '试算结果主键';
COMMENT ON COLUMN premium_quotes.user_id IS '发起试算的用户';
COMMENT ON COLUMN premium_quotes.product_id IS '试算产品';
COMMENT ON COLUMN premium_quotes.request_params IS '原始试算请求参数';
COMMENT ON COLUMN premium_quotes.result IS '统一试算响应';
COMMENT ON COLUMN premium_quotes.total_premium IS '试算年缴保费';
COMMENT ON COLUMN premium_quotes.pricing_mode IS '试算实现方式';
COMMENT ON COLUMN premium_quotes.expires_at IS '试算结果失效时间';
COMMENT ON COLUMN premium_quotes.created_at IS '创建时间';
COMMENT ON COLUMN premium_quotes.pricing_schema_id IS '使用的试算模板';
COMMENT ON COLUMN premium_quotes.schema_version IS '试算模板版本';
COMMENT ON COLUMN premium_quotes.adapter_id IS '使用的保险公司适配器';
COMMENT ON COLUMN premium_quotes.answers IS '用户填写的动态表单答案';
COMMENT ON COLUMN premium_quotes.external_request IS '发送给适配器的请求快照';
COMMENT ON COLUMN premium_quotes.external_response IS '适配器原始响应快照';

COMMENT ON TABLE orders IS '单产品投保流程末端创建的商城订单';
COMMENT ON COLUMN orders.id IS '订单主键';
COMMENT ON COLUMN orders.user_id IS '下单用户';
COMMENT ON COLUMN orders.thread_id IS '下单时关联的客服会话，可为空';
COMMENT ON COLUMN orders.order_number IS '商城订单号';
COMMENT ON COLUMN orders.confirmation_id IS '前端最终确认标识';
COMMENT ON COLUMN orders.idempotency_key IS '防止重复创建订单的幂等键';
COMMENT ON COLUMN orders.idempotency_fingerprint IS '幂等请求内容指纹';
COMMENT ON COLUMN orders.items IS '订单产品和投保信息快照';
COMMENT ON COLUMN orders.quote_ids IS '订单引用的试算结果';
COMMENT ON COLUMN orders.total_premium IS '订单总保费';
COMMENT ON COLUMN orders.recommendation_snapshot IS '下单时的推荐方案快照';
COMMENT ON COLUMN orders.status IS '订单状态';
COMMENT ON COLUMN orders.created_at IS '创建时间';
COMMENT ON COLUMN orders.updated_at IS '最后更新时间';

COMMENT ON TABLE customer_insurance_plans IS '用户确认保存的保险产品组合方案';
COMMENT ON COLUMN customer_insurance_plans.id IS '方案主键';
COMMENT ON COLUMN customer_insurance_plans.user_id IS '方案所属用户';
COMMENT ON COLUMN customer_insurance_plans.plan_name IS '方案名称';
COMMENT ON COLUMN customer_insurance_plans.summary IS '方案整体说明';
COMMENT ON COLUMN customer_insurance_plans.budget_note IS '年缴预算说明';
COMMENT ON COLUMN customer_insurance_plans.insured_profile IS '推荐时使用的被保险人画像';
COMMENT ON COLUMN customer_insurance_plans.status IS '方案投保状态';
COMMENT ON COLUMN customer_insurance_plans.annual_premium_budget IS '组合年缴预算参考';
COMMENT ON COLUMN customer_insurance_plans.version IS '方案版本号';
COMMENT ON COLUMN customer_insurance_plans.created_at IS '创建时间';
COMMENT ON COLUMN customer_insurance_plans.updated_at IS '最后更新时间';

COMMENT ON TABLE customer_insurance_plan_items IS '保险组合方案中的产品项';
COMMENT ON COLUMN customer_insurance_plan_items.id IS '方案项主键';
COMMENT ON COLUMN customer_insurance_plan_items.plan_id IS '所属保险方案';
COMMENT ON COLUMN customer_insurance_plan_items.product_id IS '推荐产品';
COMMENT ON COLUMN customer_insurance_plan_items.category IS '产品险种分类';
COMMENT ON COLUMN customer_insurance_plan_items.priority IS '方案内展示顺序';
COMMENT ON COLUMN customer_insurance_plan_items.recommendation_reason IS '推荐该产品的理由';
COMMENT ON COLUMN customer_insurance_plan_items.annual_premium_budget IS '产品年缴预算参考';
COMMENT ON COLUMN customer_insurance_plan_items.status IS '方案项投保状态';
COMMENT ON COLUMN customer_insurance_plan_items.created_at IS '创建时间';
COMMENT ON COLUMN customer_insurance_plan_items.updated_at IS '最后更新时间';

COMMENT ON TABLE policies IS '用户已承保的教学保单';
COMMENT ON COLUMN policies.id IS '保单主键';
COMMENT ON COLUMN policies.user_id IS '保单所属用户';
COMMENT ON COLUMN policies.product_id IS '承保产品';
COMMENT ON COLUMN policies.policy_number IS '保险公司保单号';
COMMENT ON COLUMN policies.status IS '保单状态';
COMMENT ON COLUMN policies.effective_at IS '保单生效时间';
COMMENT ON COLUMN policies.expires_at IS '保单到期时间';
COMMENT ON COLUMN policies.created_at IS '创建时间';
COMMENT ON COLUMN policies.updated_at IS '最后更新时间';

COMMENT ON TABLE claims IS '用户理赔案件及查询进度';
COMMENT ON COLUMN claims.id IS '理赔案件主键';
COMMENT ON COLUMN claims.user_id IS '案件所属用户';
COMMENT ON COLUMN claims.policy_id IS '关联保单';
COMMENT ON COLUMN claims.product_id IS '关联保险产品';
COMMENT ON COLUMN claims.claim_number IS '保险公司理赔案件号';
COMMENT ON COLUMN claims.claim_type IS '理赔险种类型';
COMMENT ON COLUMN claims.amount IS '案件已申请或已赔付金额，可为空';
COMMENT ON COLUMN claims.description IS '案件说明';
COMMENT ON COLUMN claims.status IS '理赔处理状态';
COMMENT ON COLUMN claims.submitted_at IS '理赔申请时间';
COMMENT ON COLUMN claims.updated_at IS '进度最后更新时间';

-- ==== V14__extend_policy_claim_demo_fields.sql ====
ALTER TABLE policies
    ADD COLUMN IF NOT EXISTS application_no VARCHAR(60),
    ADD COLUMN IF NOT EXISTS holder_name VARCHAR(80),
    ADD COLUMN IF NOT EXISTS insured_name VARCHAR(80),
    ADD COLUMN IF NOT EXISTS insured_id_no_masked VARCHAR(40),
    ADD COLUMN IF NOT EXISTS insured_phone VARCHAR(40),
    ADD COLUMN IF NOT EXISTS coverage_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS premium_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS payment_frequency VARCHAR(30),
    ADD COLUMN IF NOT EXISTS beneficiary JSONB,
    ADD COLUMN IF NOT EXISTS policy_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS coverage_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS issued_at TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS uk_policies_application_no
    ON policies(application_no)
    WHERE application_no IS NOT NULL;

COMMENT ON COLUMN policies.application_no IS '投保单号，教学演示中用于串联投保流程';
COMMENT ON COLUMN policies.holder_name IS '投保人姓名';
COMMENT ON COLUMN policies.insured_name IS '被保人姓名';
COMMENT ON COLUMN policies.insured_id_no_masked IS '被保人证件号脱敏展示';
COMMENT ON COLUMN policies.insured_phone IS '被保人联系电话';
COMMENT ON COLUMN policies.coverage_amount IS '本保单教学演示保额';
COMMENT ON COLUMN policies.premium_amount IS '本保单教学演示保费';
COMMENT ON COLUMN policies.payment_frequency IS '缴费频率，例如 annual';
COMMENT ON COLUMN policies.beneficiary IS '受益人信息快照';
COMMENT ON COLUMN policies.policy_snapshot IS '投保当时产品、方案、推荐理由等信息快照';
COMMENT ON COLUMN policies.coverage_snapshot IS '理赔演示使用的保障责任摘要快照';
COMMENT ON COLUMN policies.paid_at IS '支付完成时间';
COMMENT ON COLUMN policies.issued_at IS '承保出单时间';

