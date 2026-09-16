# 全国企业智能化转型评级系统

面向全国范围企业的智能化转型潜在客户评级系统。采集企业多维公开信息 → 规则引擎 5 维度初筛
→ DeepSeek 深度评级 → 输出 S/A/B/C/D 等级、需求标签与销售话术。

## 采集范围（改代码前必读）

全项目地域口径统一由 `engine/region.py` 提供，配置在 `config/config.yaml` 的 `region` 段：

```yaml
region:
  scope: national        # national | province | city
  province: ""           # scope=province|city 时填, 如 湖北
  city: ""               # scope=city 时填, 如 武汉
```

**不要**在任何 spider / 脚本里写死地名，一律用 `region.query(企业名)` / `region.strip_local()` /
`region.company_name_pattern()` 等接口。把 scope 改成 city + 武汉 即等价于原武汉版。

## 项目结构

- `config/` — config.yaml（含 region）、scoring_rules.yaml（评分模型唯一事实来源）、industry_keywords.yaml
- `db/` — init.sql（8 张表）、seed.sql（虚构样例）、seed_real.sql（真实企业名，工商字段留空）
- `crawler/` — Scrapy 爬虫：6 个 Spider + 5 级管道（dedup→filter→clean→validate→standardize）
- `engine/` — region.py（区域口径）、rules_engine.py、llm_client.py、report.py、websearch.py
- `skills/` — Hermes Agent Skills（rating-pipeline 为全链路运行手册）
- `scripts/` — 运维与数据脚本
- `tests/` — pytest，210 用例
- `data/potential_companies/` — 企业底池（需自备，来源见该目录 README）

## 环境要求

Python 3.11+ / PostgreSQL 16+ / Scrapy 2.11+ / DeepSeek API Key（详见 requirements.txt）

## 快速开始

```bash
/Users/henry/.local/bin/python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
createdb rating_system_national
psql -d rating_system_national -f db/init.sql
psql -d rating_system_national -f db/seed_real.sql
cp .env.example .env        # 填 DEEPSEEK_API_KEY / DATABASE_URL
python -m pytest tests/ -q
```

## 关键文档

- `README.md` — 完整说明（区域配置、命令、评分模型、已知问题）
- `docs/Hermes交接Prompt.md` — 接手开发指南
- `skills/rating-pipeline.skill.md` — 全链路脚本调用顺序与复盘
- `data/potential_companies/README.md` — 底池来源与 CSV 格式

## 注意

- `integrated_crawl.py` 会清空 news/tech/recruit/bidding 表，勿与其他爬虫并行。
- DeepSeek 评级按量计费，先用 `--limit N` 小样本验证。
- 底池必须来自真实公开名单，**禁止**用大模型生成企业名单。
