-- ============================================================
-- 全国企业智能化转型评级系统 数据库初始化脚本
-- PostgreSQL 16
-- ============================================================

-- 1. 企业主表
CREATE TABLE companies (
    id              SERIAL PRIMARY KEY,
    company_name    VARCHAR(255) NOT NULL,
    credit_code     VARCHAR(18) UNIQUE,
    registered_capital VARCHAR(50),
    capital_amount  NUMERIC(12,2),
    established_date DATE,
    legal_representative VARCHAR(100),
    business_scope  TEXT,
    registered_address TEXT,
    funding_stage   VARCHAR(20),
    status          VARCHAR(20) DEFAULT 'raw',
    industry_tags   TEXT[],
    source_url      TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_companies_status ON companies(status);
CREATE INDEX idx_companies_credit_code ON companies(credit_code);
CREATE INDEX idx_companies_name ON companies(company_name);

-- 2. 技术画像表
CREATE TABLE tech_profiles (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    tech_stack      TEXT[],
    github_org      VARCHAR(255),
    github_stars    INTEGER DEFAULT 0,
    tech_blog_url   TEXT,
    cloud_provider  VARCHAR(100),
    has_github_org  BOOLEAN DEFAULT FALSE,
    has_tech_blog   BOOLEAN DEFAULT FALSE,
    ai_job_ratio    NUMERIC(5,4) DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tech_profiles_company_id ON tech_profiles(company_id);
-- 多机同步: tech_profiles 与公司 1:1, 支撑 ON CONFLICT (company_id) 幂等写入
ALTER TABLE tech_profiles ADD CONSTRAINT uq_tech_profiles_company UNIQUE (company_id);

-- 3. 招聘信息表
CREATE TABLE recruitments (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    position_title  VARCHAR(255),
    salary_range    VARCHAR(100),
    salary_min      INTEGER,
    salary_max      INTEGER,
    tech_keywords   TEXT[],
    headcount       INTEGER DEFAULT 1,
    source_url      TEXT,
    source_name     VARCHAR(50),
    crawled_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_recruitments_company_id ON recruitments(company_id);
CREATE INDEX idx_recruitments_source ON recruitments(source_name);
-- 多机同步: 业务唯一键, 与 DedupPipeline 去重逻辑一致
ALTER TABLE recruitments ADD CONSTRAINT uq_recruitments_key
    UNIQUE (company_id, position_title, source_name);

-- 4. 新闻舆情表
CREATE TABLE news_mentions (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    title           VARCHAR(500),
    content_summary TEXT,
    source_url      TEXT,
    source_name     VARCHAR(100),
    published_at    TIMESTAMP,
    sentiment_score NUMERIC(3,2) DEFAULT 0,
    relevance_score NUMERIC(3,2) DEFAULT 0,
    is_digital_related BOOLEAN DEFAULT FALSE,
    crawled_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_news_company_id ON news_mentions(company_id);
CREATE INDEX idx_news_published ON news_mentions(published_at);
-- 多机同步: 业务唯一键 (标题截断200与DedupPipeline一致, VARCHAR(500)内安全)
ALTER TABLE news_mentions ADD CONSTRAINT uq_news_key
    UNIQUE (company_id, title, source_name);

-- 5. 招投标信息表
CREATE TABLE bidding_records (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    project_name    VARCHAR(500),
    project_type    VARCHAR(100),
    budget_amount   NUMERIC(12,2),
    is_digital      BOOLEAN DEFAULT FALSE,
    bid_date        DATE,
    source_url      TEXT,
    source_name     VARCHAR(100),
    crawled_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_bidding_company_id ON bidding_records(company_id);
CREATE INDEX idx_bidding_digital ON bidding_records(is_digital);
-- 多机同步: 业务唯一键
ALTER TABLE bidding_records ADD CONSTRAINT uq_bidding_key
    UNIQUE (company_id, project_name, source_name);

-- 6. 评级结果表
CREATE TABLE ratings (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    total_score     INTEGER,
    rating_level    CHAR(1),
    tech_score      INTEGER DEFAULT 0,
    funding_score   INTEGER DEFAULT 0,
    intent_score    INTEGER DEFAULT 0,
    team_score      INTEGER DEFAULT 0,
    industry_score  INTEGER DEFAULT 0,
    demand_tags     TEXT[],
    sales_pitch     TEXT,
    reasoning       TEXT,
    rated_by        VARCHAR(20) DEFAULT 'rules_engine',
    rated_at        TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_ratings_company_rated_by UNIQUE (company_id, rated_by)
);

CREATE INDEX idx_ratings_level ON ratings(rating_level);
CREATE INDEX idx_ratings_company_id ON ratings(company_id);
CREATE INDEX idx_ratings_total_score ON ratings(total_score);

-- 7. 爬虫任务追踪表
CREATE TABLE crawl_tasks (
    id              SERIAL PRIMARY KEY,
    task_type       VARCHAR(50),
    source_name     VARCHAR(100),
    target_url      TEXT,
    priority        INTEGER DEFAULT 5,
    status          VARCHAR(20) DEFAULT 'pending',
    retry_count     INTEGER DEFAULT 0,
    result_summary  TEXT,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_crawl_tasks_status ON crawl_tasks(status);
CREATE INDEX idx_crawl_tasks_type ON crawl_tasks(task_type);

-- 8. 评级变更日志表
CREATE TABLE rating_changelog (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    old_level       CHAR(1),
    new_level       CHAR(1),
    old_score       INTEGER,
    new_score       INTEGER,
    change_reason   TEXT,
    changed_by      VARCHAR(20),
    changed_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_changelog_company_id ON rating_changelog(company_id);
CREATE INDEX idx_changelog_changed_at ON rating_changelog(changed_at);
