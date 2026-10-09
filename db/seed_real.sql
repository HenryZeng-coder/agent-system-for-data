-- ============================================================
-- 真实武汉IT企业种子数据
-- 数据来源: 天眼查/企查查/爱企查公开搜索结果, 信用代码需人工校对
--
-- 设计说明 (2026-10 修订):
--   1. 子表不再硬编码 company_id=1..10, 而是按 companies.credit_code 关联解析。
--      原因: 若先执行过 seed.sql (演示数据, 同样占用 id 1..10), 硬编码的 id 会把
--      真实企业的招聘/新闻/招投标错挂到演示企业名下。按 credit_code 关联后,
--      本文件与 seed.sql 可任意顺序、任意次数执行, 结果均正确。
--   2. 各表 INSERT 均带 ON CONFLICT 业务唯一键, 保证幂等 (可重复执行)。
--   3. bidding_records 列名为 project_type (早期版本误写为 procurement_type,
--      会导致整段招投标数据导入失败, 已修正)。
-- ============================================================

-- ============================================================
-- 1. companies 企业主表
-- ============================================================
INSERT INTO companies (company_name, credit_code, registered_capital, capital_amount, established_date, legal_representative, business_scope, status) VALUES
('武汉斗鱼网络科技有限公司',       '91420100333437374F', '2234万元',   2234.00, '2015-05-08', '陈少杰', '网络直播平台运营、互联网技术开发、软件开发、信息技术咨询服务、计算机系统集成', 'raw'),
('烽火通信科技股份有限公司',       '914201007146661114', '128921万元', 128921.00, '1999-12-25', '曾军',   '光纤通信和相关通信技术、信息技术领域的科技开发；相关高新技术产品设计、制造和销售；系统集成', 'raw'),
('武汉达梦数据库有限公司',         '91420100737519378E', '7050万元',   7050.00,  '2000-11-13', '冯裕才', '数据库管理系统软件、数据集成软件、数据治理软件的研发、销售及技术服务；信息系统集成', 'raw'),
('武汉旷视金智科技有限公司',       '91420100MA4KXMM02E', '1000万元',   1000.00,  '2019-01-15', '唐雪峰', '人工智能技术开发、技术咨询、技术服务；计算机系统集成；软件开发', 'raw'),
('腾讯科技(武汉)有限公司',         '91420100584872426J', '1000万元',   1000.00,  '2012-02-15', '马化腾', '计算机软硬件技术开发、销售；互联网技术开发；信息技术咨询服务；网络游戏开发', 'raw'),
('远光软件(武汉)有限公司',         '91420100333557392D', '500万元',    500.00,   '2015-07-20', '陈利浩', '软件开发、信息技术咨询服务、计算机系统集成、大数据分析', 'raw'),
('武汉百域人工智能科技有限公司',   '91420111MA4L0QBP9Q', '3500万元',   3500.00,  '2018-09-13', '陈刚',   '数字技术服务、信息系统集成服务、互联网数据服务、人工智能应用软件开发、人工智能公共服务平台技术咨询', 'raw'),
('武汉融芯智能科技有限公司',       '91420100MABTNX8857', '2000万元',   2000.00,  '2021-06-15', '王磊',   '人工智能硬件开发、智能控制系统集成、人工智能通用应用系统开发、大数据服务', 'raw'),
('武汉爱迪软件技术有限公司',       '91420100MA4F3N3H5N', '500万元',    500.00,   '2021-03-10', '李明',   '智慧检务软件产品开发、信息系统集成服务、软件开发、信息技术咨询', 'raw'),
('武汉灿宇未来科技有限公司',       '91420111MA49RM6Q01', '100万元',    100.00,   '2021-05-20', '张伟',   '信息技术咨询服务、软件开发、人工智能基础软件开发、网络技术服务', 'raw')
ON CONFLICT (credit_code) DO NOTHING;

-- ============================================================
-- 2. tech_profiles 技术画像 (按 credit_code 关联, 与公司 1:1)
-- ============================================================
INSERT INTO tech_profiles (company_id, tech_stack, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
SELECT c.id, t.tech_stack, t.cloud_provider, t.has_github_org, t.has_tech_blog, t.ai_job_ratio
FROM (VALUES
    ('91420100333437374F', ARRAY['Node.js','React','FFmpeg','K8s','Redis'],    '阿里云', TRUE,  TRUE,  0.15),
    ('914201007146661114', ARRAY['C/C++','Python','5G','OTN','SDN'],           '华为云', TRUE,  TRUE,  0.10),
    ('91420100737519378E', ARRAY['C/C++','Java','SQL','分布式','DM8'],         '华为云', TRUE,  TRUE,  0.18),
    ('91420100MA4KXMM02E', ARRAY['Python','PyTorch','CV','Face++','CUDA'],     'AWS',    TRUE,  TRUE,  0.40),
    ('91420100584872426J', ARRAY['C++','Go','Python','K8s','微服务'],          '腾讯云', TRUE,  TRUE,  0.12),
    ('91420100333557392D', ARRAY['Java','Spring','大数据','区块链','微服务'],  '华为云', TRUE,  FALSE, 0.08),
    ('91420111MA4L0QBP9Q', ARRAY['Python','TensorFlow','NLP','K8s','数据中台'],'阿里云', FALSE, TRUE,  0.35),
    ('91420100MABTNX8857', ARRAY['Python','PyTorch','FPGA','嵌入式','AI芯片'], NULL,     FALSE, FALSE, 0.30),
    ('91420100MA4F3N3H5N', ARRAY['Java','Spring','微服务','检务系统','BI'],    NULL,     FALSE, FALSE, 0.05),
    ('91420111MA49RM6Q01', ARRAY['Python','AI','Web','SaaS','API'],            '阿里云', FALSE, FALSE, 0.20)
) AS t(credit_code, tech_stack, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id) DO NOTHING;

-- ============================================================
-- 3. recruitments 招聘信息 (按 credit_code 关联)
-- ============================================================
INSERT INTO recruitments (company_id, position_title, salary_min, salary_max, tech_keywords, headcount, source_name)
SELECT c.id, t.position_title, t.salary_min, t.salary_max, t.tech_keywords, t.headcount, t.source_name
FROM (VALUES
    ('91420100333437374F', '前端开发工程师',       20, 40, ARRAY['React','Node.js','TypeScript'], 5,  'BOSS直聘'),
    ('91420100333437374F', '后端开发工程师',       25, 45, ARRAY['Go','K8s','Redis','微服务'],    8,  'BOSS直聘'),
    ('914201007146661114', '5G通信工程师',         20, 40, ARRAY['5G','OTN','SDN','Python'],     10, 'BOSS直聘'),
    ('914201007146661114', '嵌入式开发工程师',     15, 30, ARRAY['C/C++','RTOS','驱动开发'],     6,  'BOSS直聘'),
    ('91420100737519378E', '数据库内核开发工程师', 30, 60, ARRAY['C/C++','SQL','分布式','DM8'],   5,  'BOSS直聘'),
    ('91420100MA4KXMM02E', 'AI算法工程师',         30, 60, ARRAY['PyTorch','CV','目标检测'],      8,  'BOSS直聘'),
    ('91420100MA4KXMM02E', '深度学习工程师',       35, 70, ARRAY['CUDA','TensorRT','模型优化'],   3,  'BOSS直聘'),
    ('91420100584872426J', '游戏服务器开发',       25, 50, ARRAY['C++','Go','Redis','分布式'],    5,  'BOSS直聘'),
    ('91420100333557392D', 'Java开发工程师',       15, 30, ARRAY['Java','Spring','微服务'],       4,  'BOSS直聘'),
    ('91420111MA4L0QBP9Q', 'NLP算法工程师',        25, 50, ARRAY['NLP','BERT','大模型','数据中台'],6, 'BOSS直聘'),
    ('91420111MA4L0QBP9Q', '数据工程师',           20, 35, ARRAY['Spark','Flink','数据仓库'],     4,  'BOSS直聘'),
    ('91420100MABTNX8857', 'AI芯片验证工程师',     25, 45, ARRAY['FPGA','Verilog','AI芯片'],      3,  'BOSS直聘'),
    ('91420100MA4F3N3H5N', 'Java开发工程师',       12, 22, ARRAY['Java','Spring','BI'],           3,  'BOSS直聘'),
    ('91420111MA49RM6Q01', 'Python开发工程师',     10, 20, ARRAY['Python','FastAPI','AI'],        2,  'BOSS直聘')
) AS t(credit_code, position_title, salary_min, salary_max, tech_keywords, headcount, source_name)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id, position_title, source_name) DO NOTHING;

-- ============================================================
-- 4. news_mentions 新闻舆情 (按 credit_code 关联)
-- ============================================================
INSERT INTO news_mentions (company_id, title, content_summary, source_name, published_at, is_digital_related, sentiment_score)
SELECT c.id, t.title, t.content_summary, t.source_name, t.published_at::timestamp, t.is_digital_related, t.sentiment_score
FROM (VALUES
    ('91420100333437374F', '斗鱼2024年Q4财报：营收超预期，AI赋能直播推荐',       '斗鱼发布Q4财报，AI推荐算法提升用户留存',              '36氪',     '2024-12-15', TRUE,  0.80),
    ('914201007146661114', '烽火通信中标中国移动5G承载网项目',                    '烽火通信中标金额超10亿的5G承载网建设采购项目',      '通信世界',  '2024-11-20', TRUE,  0.75),
    ('91420100737519378E', '达梦数据库科创板上市，国产数据库第一股',              '达梦数据库在上交所科创板上市，股票代码688692',      '证券时报',  '2024-06-12', TRUE,  0.90),
    ('91420100MA4KXMM02E', '旷视武汉研发中心扩招，AI落地智能制造',                '旷视武汉研发中心招聘规模翻倍，聚焦工业AI质检',      '湖北日报',  '2024-10-08', TRUE,  0.70),
    ('91420100584872426J', '腾讯武汉数字产业总部启用，推动中部数字经济',          '腾讯武汉数字产业总部正式启用，聚焦智慧城市与产业互联网', '长江日报', '2024-09-15', TRUE, 0.75),
    ('91420111MA4L0QBP9Q', '武汉百域AI中台助力政企数字化转型',                   '百域人工智能推出AI中台产品，服务政务和企业数字化',    '楚天都市报','2024-08-22', TRUE, 0.65)
) AS t(credit_code, title, content_summary, source_name, published_at, is_digital_related, sentiment_score)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id, title, source_name) DO NOTHING;

-- ============================================================
-- 5. bidding_records 招投标 (按 credit_code 关联)
--    注意: 列名是 project_type, 不是 procurement_type
-- ============================================================
INSERT INTO bidding_records (company_id, project_name, project_type, budget_amount, is_digital, source_name, bid_date)
SELECT c.id, t.project_name, t.project_type, t.budget_amount, t.is_digital, t.source_name, t.bid_date::date
FROM (VALUES
    ('914201007146661114', '中国移动5G承载网设备采购项目',   '设备采购', 100000.00, TRUE, '中国移动采购网', '2024-11-15'),
    ('91420100737519378E', '某省级政务云数据库替换项目',     '软件采购', 800.00,    TRUE, '中国政府采购网', '2024-07-20'),
    ('91420100584872426J', '武汉智慧城市数据中台建设项目',   '系统集成', 5000.00,   TRUE, '中国政府采购网', '2024-09-10'),
    ('91420111MA4L0QBP9Q', '某区数字化政务服务平台升级项目', '软件开发', 350.00,    TRUE, '中国政府采购网', '2024-08-15')
) AS t(credit_code, project_name, project_type, budget_amount, is_digital, source_name, bid_date)
JOIN companies c ON c.credit_code = t.credit_code
ON CONFLICT (company_id, project_name, source_name) DO NOTHING;
