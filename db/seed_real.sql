-- ============================================================
-- 全国企业智能化转型评级系统 — 样例种子数据 (用于打通流水线)
--
-- 说明:
--   1. 这里只放 company_name, 其余工商字段全部留空, 由 business_spider /
--      scripts/enrich_bizinfo.py 采集补全。**不要**把它当作已核实数据使用。
--   2. credit_code 故意留 NULL (Postgres 允许多行 NULL), 避免伪造信用代码;
--      等爬虫补全后再写回。
--   3. 若要换成真实企业池, 用:
--        python scripts/import_company_pool.py --csv <你的名单.csv>
--      名单来源建议: 各省市工信/经信部门公示的「数字化转型试点、智能工厂、
--      人工智能应用服务商」等认定名单 (免费公开)。
-- ============================================================

-- ============================================================
-- 1. companies 企业主表 (status='raw' → 待爬取)
-- ============================================================
INSERT INTO companies
    (company_name, credit_code, registered_capital, capital_amount,
     established_date, legal_representative, business_scope, funding_stage,
     status, industry_tags)
VALUES
    ('用友网络科技股份有限公司',        NULL, NULL, NULL, NULL, NULL, '企业管理软件、云服务、企业数字化转型解决方案',          NULL, 'raw', '{"软件","云服务","企业数字化"}'),
    ('东软集团股份有限公司',            NULL, NULL, NULL, NULL, NULL, '行业应用软件、医疗信息化、智能汽车软件、系统集成',      NULL, 'raw', '{"软件","医疗信息化","汽车电子"}'),
    ('宝信软件股份有限公司',            NULL, NULL, NULL, NULL, NULL, '工业软件、工业互联网平台、智能制造解决方案、数据中心',  NULL, 'raw', '{"工业软件","工业互联网","智能制造"}'),
    ('广联达科技股份有限公司',          NULL, NULL, NULL, NULL, NULL, '建筑行业软件、BIM 平台、工程造价软件、数字建造',        NULL, 'raw', '{"建筑信息化","BIM","工业软件"}'),
    ('中控技术股份有限公司',            NULL, NULL, NULL, NULL, NULL, '工业自动化控制系统、DCS、工业软件、智能制造',            NULL, 'raw', '{"工业自动化","智能制造","工业软件"}'),
    ('浪潮软件股份有限公司',            NULL, NULL, NULL, NULL, NULL, '云计算、大数据平台、政务信息化、行业软件',              NULL, 'raw', '{"云计算","大数据","数字政府"}'),
    ('东方国信科技股份有限公司',        NULL, NULL, NULL, NULL, NULL, '大数据平台、数据治理、工业互联网、人工智能应用',        NULL, 'raw', '{"大数据","工业互联网","人工智能"}'),
    ('汉得信息技术股份有限公司',        NULL, NULL, NULL, NULL, NULL, '企业信息化咨询、ERP 实施、数字化转型服务',              NULL, 'raw', '{"信息技术服务","ERP","数字化咨询"}'),
    ('石化盈科信息技术有限责任公司',    NULL, NULL, NULL, NULL, NULL, '石油化工行业信息化、工业互联网平台、智能制造',          NULL, 'raw', '{"工业互联网","智能制造","行业信息化"}'),
    ('金蝶软件(中国)有限公司',          NULL, NULL, NULL, NULL, NULL, '企业管理软件、云 ERP、财务云、企业数字化服务',          NULL, 'raw', '{"软件","SaaS","云服务"}')
ON CONFLICT (credit_code) DO NOTHING;

-- ============================================================
-- 2. tech_profiles 技术画像 (company_id 对应上面 1..10 的插入顺序)
-- ============================================================
INSERT INTO tech_profiles
    (company_id, tech_stack, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
VALUES
    (1,  ARRAY['Java','Spring','Kubernetes','MySQL'], '华为云',   TRUE,  TRUE,  0.18),
    (2,  ARRAY['Java','C++','Kubernetes','Flink'],    '阿里云',   TRUE,  TRUE,  0.15),
    (3,  ARRAY['Java','Python','Kafka','Flink'],      '华为云',   FALSE, TRUE,  0.20),
    (4,  ARRAY['C++','TypeScript','WebGL','K8s'],     '阿里云',   TRUE,  TRUE,  0.12),
    (5,  ARRAY['C','C++','Python','Docker'],          '阿里云',   FALSE, TRUE,  0.10),
    (6,  ARRAY['Java','Go','Hadoop','Spark'],         '浪潮云',   FALSE, TRUE,  0.16),
    (7,  ARRAY['Java','Scala','Hadoop','Flink'],      '阿里云',   TRUE,  TRUE,  0.22),
    (8,  ARRAY['Java','SAP','Python','Airflow'],      '腾讯云',   FALSE, FALSE, 0.08),
    (9,  ARRAY['Java','Go','Kubernetes','Pulsar'],    '华为云',   FALSE, TRUE,  0.14),
    (10, ARRAY['Java','Go','SaaS','Kubernetes'],      '金蝶云',   TRUE,  TRUE,  0.25);

-- ============================================================
-- 3. recruitments 招聘信息
-- ============================================================
INSERT INTO recruitments
    (company_id, position_title, salary_range, salary_min, salary_max,
     tech_keywords, headcount, source_name)
VALUES
    (1,  'AI 算法工程师',       '30-50K', 30, 50, ARRAY['Python','PyTorch','大模型'], 3, 'BOSS直聘'),
    (1,  '云平台开发工程师',    '25-40K', 25, 40, ARRAY['Kubernetes','Go'],          5, '猎聘'),
    (3,  '工业互联网架构师',    '40-65K', 40, 65, ARRAY['工业互联网','Flink','IoT'], 2, 'BOSS直聘'),
    (3,  '智能制造实施顾问',    '20-35K', 20, 35, ARRAY['MES','数字化工厂'],         4, '智联招聘'),
    (5,  '工业软件工程师',      '20-35K', 20, 35, ARRAY['C++','DCS','PLC'],          4, 'BOSS直聘'),
    (7,  '大数据开发工程师',    '25-45K', 25, 45, ARRAY['Spark','Flink','数仓'],     6, 'BOSS直聘'),
    (7,  '数据治理专家',        '35-55K', 35, 55, ARRAY['数据治理','元数据'],        2, '猎聘'),
    (10, 'SaaS 产品经理',       '25-40K', 25, 40, ARRAY['SaaS','云ERP'],            3, 'BOSS直聘'),
    (10, '大模型应用工程师',    '30-50K', 30, 50, ARRAY['LLM','RAG','Python'],       2, '猎聘');

-- ============================================================
-- 4. news_mentions 新闻舆情
-- ============================================================
INSERT INTO news_mentions
    (company_id, title, content_summary, source_name, published_at,
     is_digital_related, sentiment_score)
VALUES
    (1,  '用友发布企业级 AI 应用平台，推动企业管理智能化',
         '用友在年度峰会上发布 AI 应用平台，覆盖财务、人力、供应链等场景', '36氪', '2026-01-15', TRUE, 0.80),
    (3,  '宝信软件中标某大型钢铁集团智能制造改造项目',
         '项目包含工业互联网平台建设与产线数字化改造，合同金额逾亿元', '中国证券网', '2026-02-08', TRUE, 0.75),
    (5,  '中控技术发布新一代工业控制系统，支持全流程数字孪生',
         '新系统面向流程工业，集成数字孪生与 AI 优化模块', '证券时报', '2026-02-20', TRUE, 0.70),
    (7,  '东方国信数据中台通过信创适配认证',
         '产品完成与国产数据库、操作系统的兼容性认证', '中国信息化周报', '2026-01-28', TRUE, 0.65),
    (10, '金蝶云服务收入同比增长，中小企业上云需求旺盛',
         '云订阅收入持续增长，管理层表示将加大 AI 产品投入', '财联社', '2026-03-05', TRUE, 0.72),
    (2,  '东软医疗信息化业务承压，公司推进业务结构调整',
         '受行业招标节奏影响，相关板块收入短期波动', '证券时报', '2026-02-11', FALSE, -0.30);

-- ============================================================
-- 5. bidding_records 招投标 (注意: 列名是 project_type, 非 procurement_type)
-- ============================================================
INSERT INTO bidding_records
    (company_id, project_name, project_type, budget_amount, is_digital,
     bid_date, source_name)
VALUES
    (3, '某钢铁集团智能制造平台建设项目',   '信息化建设', 12000.00, TRUE,  '2026-02-06', '中国政府采购网'),
    (3, '工业互联网标识解析节点建设项目',   '信息化建设',  3500.00, TRUE,  '2026-01-20', '中国政府采购网'),
    (6, '某省级政务云平台扩容采购项目',     '设备采购',    8600.00, TRUE,  '2026-02-18', '中国政府采购网'),
    (7, '某市数据中台及数据治理服务项目',   '服务采购',    4200.00, TRUE,  '2026-03-02', '中国政府采购网'),
    (9, '某石化企业智能工厂试点建设项目',   '信息化建设', 15000.00, TRUE,  '2026-01-30', '中国政府采购网');
