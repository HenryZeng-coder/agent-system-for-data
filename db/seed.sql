-- 测试种子数据 (10家示例企业)

INSERT INTO companies (company_name, credit_code, registered_capital, capital_amount, business_scope, status, industry_tags)
VALUES
    ('武汉智云科技有限公司', '91420100MA4K2X1A3B', '5000万元', 5000.00, '人工智能软件开发、云计算、大数据分析', 'raw', '{"人工智能","云计算"}'),
    ('光谷数据科技有限公司', '91420100MA4K3Y2B4C', '1000万元', 1000.00, '大数据平台开发、数字化转型咨询', 'raw', '{"大数据","数字化转型"}'),
    ('武汉华信软件有限公司', '91420100MA4K4Z3C5D', '300万元', 300.00, '网络工程、硬件销售、监控设备', 'raw', '{"网络工程","硬件"}'),
    ('武汉创新云计算有限公司', '91420100MA4K5A4D6E', '8000万元', 8000.00, '云计算平台、AI中台、系统集成', 'raw', '{"云计算","AI中台","系统集成"}'),
    ('武汉传统信息技术有限公司', '91420100MA4K6B5E7F', '200万元', 200.00, '办公设备销售、维修服务', 'raw', '{"运维","硬件"}'),
    ('武汉星辰智能有限公司', '91420100MA4K7C6F8G', '2000万元', 2000.00, '智能安防、物联网、软件开发', 'raw', '{"智能安防","物联网","软件开发"}'),
    ('武汉数字转型咨询有限公司', '91420100MA4K8D7G9H', '1500万元', 1500.00, '数字化转型咨询、大模型应用、数据治理', 'raw', '{"数字化转型","大模型","数据治理"}'),
    ('武汉基础网络有限公司', '91420100MA4K9E8H0I', '100万元', 100.00, '网络布线、弱电工程', 'raw', '{"网络工程","监控"}'),
    ('武汉云端科技有限公司', '91420100MA4L0F9I1J', '3000万元', 3000.00, '云原生开发、DevOps、容器化', 'raw', '{"云原生","DevOps"}'),
    ('武汉老牌软件有限公司', '91420100MA4L1G0J2K', '800万元', 800.00, '传统ERP开发、软件外包', 'raw', '{"软件开发","外包"}');

-- 示例技术画像
INSERT INTO tech_profiles (company_id, tech_stack, github_org, github_stars, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
VALUES
    (1, '{"Python","PyTorch","Kubernetes","AWS"}', 'zhiyun-tech', 1200, 'AWS', TRUE, TRUE, 0.35),
    (2, '{"Java","Spark","Hadoop","阿里云"}', NULL, 0, '阿里云', FALSE, TRUE, 0.15),
    (3, NULL, NULL, 0, NULL, FALSE, FALSE, 0.0),
    (4, '{"Go","Docker","Kubernetes","Azure"}', 'chuangxin-cloud', 3500, 'Azure', TRUE, TRUE, 0.25),
    (5, NULL, NULL, 0, NULL, FALSE, FALSE, 0.0),
    (6, '{"Python","TensorFlow","React"}', 'xingchen-ai', 800, '腾讯云', TRUE, FALSE, 0.22),
    (7, '{"Python","LangChain","GPT"}', 'digital-transform', 300, '阿里云', TRUE, TRUE, 0.40),
    (8, NULL, NULL, 0, NULL, FALSE, FALSE, 0.0),
    (9, '{"Go","Docker","Terraform","阿里云"}', 'yunduan-dev', 600, '阿里云', TRUE, TRUE, 0.18),
    (10, '{"Java","Spring"}', NULL, 0, NULL, FALSE, FALSE, 0.05);

-- 示例招聘数据
INSERT INTO recruitments (company_id, position_title, salary_range, salary_min, salary_max, tech_keywords, headcount, source_name)
VALUES
    (1, 'AI算法工程师', '25K-45K', 25, 45, '{"深度学习","NLP","大模型"}', 10, 'BOSS直聘'),
    (1, '云架构师', '30K-50K', 30, 50, '{"AWS","Kubernetes","微服务"}', 5, 'BOSS直聘'),
    (2, '大数据工程师', '15K-25K', 15, 25, '{"Spark","Flink","Hadoop"}', 8, '拉勾'),
    (4, '云原生开发工程师', '20K-35K', 20, 35, '{"Go","Docker","K8s"}', 12, 'BOSS直聘'),
    (4, 'DevOps工程师', '18K-30K', 18, 30, '{"CI/CD","Terraform"}', 6, '猎聘'),
    (6, 'AI产品经理', '20K-35K', 20, 35, '{"AI","产品规划"}', 3, 'BOSS直聘'),
    (7, '大模型应用开发', '25K-40K', 25, 40, '{"LLM","LangChain","Prompt"}', 8, 'BOSS直聘'),
    (9, 'SRE工程师', '15K-25K', 15, 25, '{"Linux","Docker","监控"}', 4, '拉勾'),
    (10, 'Java开发工程师', '10K-18K', 10, 18, '{"Java","Spring"}', 3, 'BOSS直聘');

-- 示例新闻
INSERT INTO news_mentions (company_id, title, content_summary, source_name, published_at, sentiment_score, relevance_score, is_digital_related)
VALUES
    (1, '武汉智云科技完成A轮融资', '公司获得2亿元A轮融资，将加大AI大模型研发投入', '百度新闻', NOW() - INTERVAL '3 days', 0.8, 0.9, TRUE),
    (4, '创新云计算发布AI中台产品', '公司正式推出企业级AI中台解决方案', '搜狗新闻', NOW() - INTERVAL '5 days', 0.7, 0.85, TRUE),
    (7, '数字转型咨询获政府数字化转型项目', '中标武汉市政数局数字化转型咨询项目', '中国政府采购网', NOW() - INTERVAL '2 days', 0.6, 0.9, TRUE);

-- 示例招投标
INSERT INTO bidding_records (company_id, project_name, project_type, budget_amount, is_digital, bid_date, source_name)
VALUES
    (7, '武汉市政数局数字化转型规划项目', '咨询服务', 280.00, TRUE, CURRENT_DATE - INTERVAL '2 days', '中国政府采购网'),
    (4, '某银行云平台建设采购项目', '信息化建设', 1500.00, TRUE, CURRENT_DATE - INTERVAL '10 days', '中国政府采购网');
