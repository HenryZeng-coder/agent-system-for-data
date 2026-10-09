-- ============================================================
-- 测试种子数据 (10 家示例企业, 纯虚构, 仅用于打通流水线)
-- 注意: 信用代码为占位值, 不是真实统一社会信用代码
--
-- 设计说明 (2026-10 修订):
--   子表不再硬编码 company_id=1..10, 改为按 companies.credit_code 关联解析,
--   并加 ON CONFLICT 业务唯一键。这样本文件与 db/seed_real.sql 可任意顺序、
--   任意次数执行, 结果均正确 (早期版本在 seed_real.sql 之后执行会把招聘/
--   新闻错挂到别的企业 id 上)。验证真实样例请用 db/seed_real.sql。
-- ============================================================

-- ============================================================
-- 1. companies 企业主表
-- ============================================================
INSERT INTO companies (company_name, credit_code, registered_capital, capital_amount, business_scope, status, industry_tags)
VALUES
    ('示例智云科技有限公司',     '91000000MA4K2X1A3B', '5000万元', 5000.00, '人工智能软件开发、云计算、大数据分析', 'raw', '{"人工智能","云计算"}'),
    ('高新数据科技有限公司',     '91000000MA4K3Y2B4C', '1000万元', 1000.00, '大数据平台开发、数字化转型咨询',      'raw', '{"大数据","数字化转型"}'),
    ('示例华信软件有限公司',     '91000000MA4K4Z3C5D', '300万元',  300.00,  '网络工程、硬件销售、监控设备',        'raw', '{"网络工程","硬件"}'),
    ('示例创新云计算有限公司',   '91000000MA4K5A4D6E', '8000万元', 8000.00, '云计算平台、AI中台、系统集成',        'raw', '{"云计算","AI中台","系统集成"}'),
    ('示例传统信息技术有限公司', '91000000MA4K6B5E7F', '200万元',  200.00,  '办公设备销售、维修服务',              'raw', '{"运维","硬件"}'),
    ('示例星辰智能有限公司',     '91000000MA4K7C6F8G', '2000万元', 2000.00, '智能安防、物联网、软件开发',          'raw', '{"智能安防","物联网","软件开发"}'),
    ('示例数字转型咨询有限公司', '91000000MA4K8D7G9H', '1500万元', 1500.00, '数字化转型咨询、大模型应用、数据治理', 'raw', '{"数字化转型","大模型","数据治理"}'),
    ('示例基础网络有限公司',     '91000000MA4K9E8H0I', '100万元',  100.00,  '网络布线、弱电工程',                  'raw', '{"网络工程","监控"}'),
    ('示例云端科技有限公司',     '91000000MA4L0F9I1J', '3000万元', 3000.00, '云原生开发、DevOps、容器化',          'raw', '{"云原生","DevOps"}'),
    ('示例老牌软件有限公司',     '91000000MA4L1G0J2K', '800万元',  800.00,  '传统ERP开发、软件外包',               'raw', '{"软件开发","外包"}')
ON CONFLICT (credit_code) DO NOTHING;

-- ============================================================
-- 2. tech_profiles 技术画像 (按 credit_code 关联, 与公司 1:1)
-- ============================================================
INSERT INTO tech_profiles (company_id, tech_stack, github_org, github_stars, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
SELECT c.id, t.tech_stack, t.github_org, t.github_stars, t.cloud_provider, t.has_github_org, t.has_tech_blog, t.ai_job_ratio
FROM (VALUES
    ('91000000MA4K2X1A3B', ARRAY['Python','PyTorch','Kubernetes','AWS'], 'zhiyun-tech',       1200, 'AWS',    TRUE,  TRUE,  0.35),
    ('91000000MA4K3Y2B4C', ARRAY['Java','Spark','Hadoop','阿里云'],      NULL,                0,    '阿里云', FALSE, TRUE,  0.15),
    ('91000000MA4K4Z3C5D', NULL::text[],                                 NULL,                0,    NULL,     FALSE, FALSE, 0.0),
    ('91000000MA4K5A4D6E', ARRAY['Go','Docker','Kubernetes','Azure'],    'chuangxin-cloud',   3500, 'Azure',  TRUE,  TRUE,  0.25),
    ('91000000MA4K6B5E7F', NULL::text[],                                 NULL,                0,    NULL,     FALSE, FALSE, 0.0),
    ('91000000MA4K7C6F8G', ARRAY['Python','TensorFlow','React'],         'xingchen-ai',       800,  '腾讯云', TRUE,  FALSE, 0.22),
    ('91000000MA4K8D7G9H', ARRAY['Python','LangChain','GPT'],            'digital-transform', 300,  '阿里云', TRUE,  TRUE,  0.40),
    ('91000000MA4K9E8H0I', NULL::text[],                                 NULL,                0,    NULL,     FALSE, FALSE, 0.0),
    ('91000000MA4L0F9I1J', ARRAY['Go','Docker','Terraform','阿里云'],    'yunduan-dev',       600,  '阿里云', TRUE,  TRUE,  0.18),
    ('91000000MA4L1G0J2K', ARRAY['Java','Spring'],                       NULL,                0,    NULL,     FALSE, FALSE, 0.05)
) AS t(credit_code, tech_stack, github_org, github_stars, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id) DO NOTHING;

-- ============================================================
-- 3. recruitments 招聘数据 (按 credit_code 关联)
-- ============================================================
INSERT INTO recruitments (company_id, position_title, salary_range, salary_min, salary_max, tech_keywords, headcount, source_name)
SELECT c.id, t.position_title, t.salary_range, t.salary_min, t.salary_max, t.tech_keywords, t.headcount, t.source_name
FROM (VALUES
    ('91000000MA4K2X1A3B', 'AI算法工程师',    '25K-45K', 25, 45, ARRAY['深度学习','NLP','大模型'],   10, 'BOSS直聘'),
    ('91000000MA4K2X1A3B', '云架构师',        '30K-50K', 30, 50, ARRAY['AWS','Kubernetes','微服务'], 5,  'BOSS直聘'),
    ('91000000MA4K3Y2B4C', '大数据工程师',    '15K-25K', 15, 25, ARRAY['Spark','Flink','Hadoop'],    8,  '拉勾'),
    ('91000000MA4K5A4D6E', '云原生开发工程师', '20K-35K', 20, 35, ARRAY['Go','Docker','K8s'],        12, 'BOSS直聘'),
    ('91000000MA4K5A4D6E', 'DevOps工程师',    '18K-30K', 18, 30, ARRAY['CI/CD','Terraform'],         6,  '猎聘'),
    ('91000000MA4K7C6F8G', 'AI产品经理',      '20K-35K', 20, 35, ARRAY['AI','产品规划'],             3,  'BOSS直聘'),
    ('91000000MA4K8D7G9H', '大模型应用开发',  '25K-40K', 25, 40, ARRAY['LLM','LangChain','Prompt'],  8,  'BOSS直聘'),
    ('91000000MA4L0F9I1J', 'SRE工程师',       '15K-25K', 15, 25, ARRAY['Linux','Docker','监控'],     4,  '拉勾'),
    ('91000000MA4L1G0J2K', 'Java开发工程师',  '10K-18K', 10, 18, ARRAY['Java','Spring'],             3,  'BOSS直聘')
) AS t(credit_code, position_title, salary_range, salary_min, salary_max, tech_keywords, headcount, source_name)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id, position_title, source_name) DO NOTHING;

-- ============================================================
-- 4. news_mentions 新闻舆情 (按 credit_code 关联)
-- ============================================================
INSERT INTO news_mentions (company_id, title, content_summary, source_name, published_at, sentiment_score, relevance_score, is_digital_related)
SELECT c.id, t.title, t.content_summary, t.source_name, NOW() - make_interval(days => t.days_ago), t.sentiment_score, t.relevance_score, TRUE
FROM (VALUES
    ('91000000MA4K2X1A3B', '示例智云科技完成A轮融资',         '公司获得2亿元A轮融资，将加大AI大模型研发投入', '百度新闻',       3, 0.8, 0.9),
    ('91000000MA4K5A4D6E', '创新云计算发布AI中台产品',        '公司正式推出企业级AI中台解决方案',           '搜狗新闻',       5, 0.7, 0.85),
    ('91000000MA4K8D7G9H', '数字转型咨询获政府数字化转型项目', '中标示例市政数局数字化转型咨询项目',         '中国政府采购网', 2, 0.6, 0.9)
) AS t(credit_code, title, content_summary, source_name, days_ago, sentiment_score, relevance_score)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id, title, source_name) DO NOTHING;

-- ============================================================
-- 5. bidding_records 招投标 (按 credit_code 关联)
-- ============================================================
INSERT INTO bidding_records (company_id, project_name, project_type, budget_amount, is_digital, bid_date, source_name)
SELECT c.id, t.project_name, t.project_type, t.budget_amount, TRUE, CURRENT_DATE - make_interval(days => t.days_ago), t.source_name
FROM (VALUES
    ('91000000MA4K8D7G9H', '示例市政数局数字化转型规划项目', '咨询服务',   280.00,  2,  '中国政府采购网'),
    ('91000000MA4K5A4D6E', '某银行云平台建设采购项目',       '信息化建设', 1500.00, 10, '中国政府采购网')
) AS t(credit_code, project_name, project_type, budget_amount, days_ago, source_name)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id, project_name, source_name) DO NOTHING;
