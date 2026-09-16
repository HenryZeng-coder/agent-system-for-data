# 武汉IT企业智能评级系统 (E-InfoInsight)

面向武汉地区 IT 企业的智能化转型潜在客户评级系统：从公开渠道采集企业工商/技术/招聘/舆情/招投标
4 类数据，先用**规则引擎**做 5 维度加权初筛，再由 **DeepSeek** 做深度评级，输出 S/A/B/C/D 等级、
需求标签与销售话术，形成可直接使用的销售线索清单。

- 代码仓库: `E-InfoInsigth-agent-codes`
- 技术栈: Python 3.11 + Scrapy 2.11 + PostgreSQL + DeepSeek API
- 编排方式: Hermes Agent Skills (`skills/`) + 运维脚本 (`scripts/`)

---

## 一、目录结构

```
E-InfoInsigth-agent-codes/
├── config/                   # 全局配置
│   ├── config.yaml           # 数据库/DeepSeek/爬虫/调度/报告配置
│   ├── scoring_rules.yaml    # 5 维度评分规则（评分模型唯一事实来源）
│   └── industry_keywords.yaml
├── db/
│   ├── init.sql              # 建表 DDL（8 张表 + 索引 + 多机同步唯一约束）
│   ├── seed.sql              # 测试种子数据
│   └── seed_real.sql         # 真实武汉 IT 企业种子数据（10 家，含信用代码）
├── crawler/                  # Scrapy 爬虫
│   ├── scrapy.cfg
│   ├── wuhan_it_crawler/
│   │   ├── items.py          # 6 个 Item: Company/TechProfile/Recruitment/NewsMention/Bidding/CrawlTask
│   │   ├── settings.py       # 5 级管道注册 + 中间件
│   │   ├── middlewares.py
│   │   ├── spiders/          # 6 个 Spider
│   │   │   ├── business_spider.py      (name=business)     工商信息
│   │   │   ├── tech_spider.py          (name=tech)         技术画像
│   │   │   ├── recruitment_spider.py   (name=recruitment)  招聘
│   │   │   ├── news_spider.py          (name=news)         新闻舆情
│   │   │   ├── bidding_spider.py       (name=bidding)      招投标
│   │   │   └── websearch_spider.py     (name=websearch)    聚合搜索
│   │   └── pipelines/        # 5 级管道: dedup(100)→filter(200)→clean(300)→validate(400)→standardize(500)
│   └── utils/                # 反爬工具: proxy_pool / ua_rotator / captcha_solver / anti_detect
├── engine/                   # 评级引擎
│   ├── rules_engine.py       # RatingRulesEngine — 5 维度加权评分（CLI: --mode incremental|full）
│   ├── llm_client.py         # LLMRatingClient — DeepSeek 批量评级 (CLI: --mode/--levels/--limit)
│   ├── report.py             # ReportGenerator — 日报 / 线索 CSV+Excel 导出（--mode daily|leads|notify）
│   ├── data_pipeline.py      # 非 Scrapy 场景的 5 级数据管道（与爬虫管道逻辑对齐）
│   ├── websearch.py          # 多引擎搜索聚合（百度/搜狗/必应/360/头条，失败降级 + URL 去重）
│   └── prompts/              # analysis_prompt.md + few_shot_examples.json（覆盖 S/A/B/C/D）
├── skills/                   # Hermes Agent Skills
│   ├── rating-pipeline.skill.md   # 全链路运行手册（推荐入口，含脚本调用顺序）
│   ├── rating-crawl.skill.md      # 爬虫编排
│   ├── rating-score.skill.md      # 规则引擎评分
│   ├── rating-analyze.skill.md    # DeepSeek 深度评级
│   └── rating-report.skill.md     # 报告与线索导出
├── scripts/                  # 运维 / 数据脚本（见第五节）
├── tests/                    # pytest 单元测试（210 个用例）
├── data/
│   ├── potential_companies/  # 企业底池（0_government_certified* 为真实政府名单）
│   ├── exports/              # 数据表全量 CSV 导出
│   ├── reports/              # 日报 / 线索 / individual.csv / 验证报告
│   └── sync/                 # 多机同步用的中间 CSV
├── logs/                     # 运行日志 + 运行总结
├── docs/                     # 开发流程 / 交接文档 / 同步方案
├── CLAUDE.md                 # 项目速览（供 Agent 读取）
├── requirements.txt          # 运行依赖
└── requirements-dev.txt      # 开发依赖 (pytest / ipython)
```

---

## 二、数据流与状态机

```
                 crawler(6 spiders)          rules_engine          llm_client            report
  companies ────────────────────────►  status='raw'
     ▲                                        │                      │                    │
     │                                        ▼                      ▼                    ▼
     └── 政府名单导入/工商补全           status='scored'  ──►  status='rated'  ──►  data/reports/*
                                          (规则初筛)          (DeepSeek 深度评级)    日报/线索/individual.csv
```

- `companies.status`: `raw → scored → rated`（`filtered` 为未达 IT 行业过滤的企业）
- `ratings.rated_by`: `rules_engine`（规则引擎） / `deepseek`（大模型），同一企业可同时存在两条记录
- 规则引擎初筛达标线：`level_thresholds.B = 40`，即 B 级及以上送 DeepSeek 深度评级
- 人工核验/去重条件：`credit_code` 唯一（爬虫 DedupPipeline 与数据库约束双层保障）

---

## 三、评分模型

规则定义全部位于 `config/scoring_rules.yaml`，总分上限 100。

| 维度 | 权重上限 | 主要计分项 |
|------|---------|-----------|
| `tech_investment` 技术投入 | 30 | AI 岗位占比 ≥0.2 → 15；云厂商 → 5；GitHub 组织 → 5；技术博客 → 5；经营范围兜底（含"人工智能"→ 下限 10） |
| `funding` 资金实力 | 25 | 融资阶段 B/C→15、A→10、D→5；注册资本 ≥1000 万 → 5；规模梯度 ≥5亿→8 / ≥1亿→5 / ≥5000万→3（取最高档） |
| `transformation_intent` 转型意向 | 30 | 新闻关键词命中 5 分/个（上限 20）；数字化招投标 → 10；经营范围意图 5/5/3；跨维度加成（技术≥25 或 资本≥5000万且技术≥10 → +5） |
| `team_size` 团队规模 | 15 | 招聘岗位数 50→15 / 20→10 / 5→5；招聘数据稀疏时用注册资本兜底（≥5亿→≥10，≥5000万→≥5） |
| `industry_match` 行业匹配 | 10 | 高匹配关键词 +2/个，低匹配关键词 −1/个 |

**等级阈值**（`level_thresholds`）：`S ≥ 80`、`A ≥ 60`、`B ≥ 40`、`C ≥ 20`、`D < 20`

---

## 四、快速开始

> 注意：`CLAUDE.md` 中提到的 `bash scripts/setup.sh` 在仓库中**不存在**，请按下列步骤手动搭建。

### 4.1 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 本机系统 `python3` 为 3.9，无法使用；请用 uv 安装的 3.11 |
| PostgreSQL | 16+ | 本机实测 18.4 (Homebrew) |
| Playwright Chromium | - | 供 scrapy-playwright 使用 |

### 4.2 安装步骤

```bash
cd /Users/henry/Desktop/repository/E-InfoInsigth-agent-codes

# 1. 创建虚拟环境（本机 3.11 解释器路径）
/Users/henry/.local/bin/python3.11 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt -r requirements-dev.txt

# 3. 安装 Playwright 浏览器
playwright install chromium

# 4. 启动 PostgreSQL 并创建数据库
brew services start postgresql@18        # 若装的是 16 则改为 postgresql@16
createdb rating_system

# 5. 初始化表结构 + 种子数据
psql -d rating_system -f db/init.sql
psql -d rating_system -f db/seed_real.sql    # 真实企业种子（推荐）
# psql -d rating_system -f db/seed.sql       # 或使用测试种子数据

# 6. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实值（.env 已在 .gitignore 中，切勿提交）

# 7. 给运维脚本添加执行权限
chmod +x scripts/*.sh
```

`.env` 需要以下变量：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（DeepSeek 评级必需） |
| `DATABASE_URL` | 例：`postgresql://<你的PG用户>@localhost:5432/rating_system`（`.env.example` 里是旧机器的 `kc` 用户，本机需替换） |
| `PROXY_POOL_API` | 代理池 API 地址（`config.yaml` 中 `proxy.enabled: true`，无代理可关闭） |
| `HERMES_WORKDIR` | 项目绝对路径 |

### 4.3 验证安装

```bash
source .venv/bin/activate

# 数据库连通 + 当前企业状态分布
psql -d rating_system -c "SELECT status, count(*) FROM companies GROUP BY status"

# 爬虫注册（期望列出 business, tech, recruitment, news, bidding, websearch）
cd crawler && scrapy list && cd ..

# 核心模块导入
python -c "from engine.rules_engine import RatingRulesEngine; print('OK')"
python -c "from engine.llm_client import LLMRatingClient; print('OK')"
python -c "from engine.report import ReportGenerator; print('OK')"

# 单元测试（期望 210 passed）
python -m pytest tests/ -q
```

---

## 五、常用命令

### 5.1 全链路（推荐）

直接加载 `skills/rating-pipeline.skill.md`——它是持续更新的运行手册，含脚本调用顺序、
效率优化参考与复盘机制。核心顺序：

```bash
# 1) 集成爬取（4 维度：新闻 → 技术画像 → 招聘 → 招投标；会先清空关联表，勿与其他爬虫并行）
python scripts/integrated_crawl.py > logs/run_$(date +%Y%m%d_%H%M%S).log 2>&1

# 2) 规则引擎评分
python engine/rules_engine.py --mode full          # 或 --mode incremental

# 3) DeepSeek 深度评级（规则引擎达标企业）
#    入口二选一，两者共用 engine.llm_client.run_batch_rating 同一份实现：
python engine/llm_client.py --mode full            # 或 --mode incremental
python scripts/run_deepseek_rating.py full         # 位置参数 full|incremental|hot_track

#    追加参数: --levels S,A 只重评指定等级 (热点追踪) | --limit N 小样本验证
python engine/llm_client.py --mode hot_track --levels S,A --limit 5

# 4) 结果验证（规则校验 + 评分合理性/数据真实性判读 → verification_<ts>.md）
python scripts/verify_results.py --limit 50

# 5) 导出最终结果 individual.csv（15 列，规则 + LLM 双评级）
python scripts/export_individual.py

# 6) 日报 / 线索导出
python engine/report.py --mode daily  --date $(date +%Y-%m-%d)
python engine/report.py --mode leads  --levels S,A
```

### 5.2 运维脚本（`scripts/*.sh`）

| 脚本 | 用途 |
|------|------|
| `daily_update.sh` | 每日增量：增量爬取 → 增量评分 → DeepSeek 增量评级 → 日报 |
| `full_scan.sh` | 全量重跑：6 个 spider 全量 → 全量评分 → 全量评级 → 报告 |
| `hot_track.sh` | 热点追踪：S/A 级企业新闻 → 重新评级（`--levels S,A`）→ 追踪报告 |
| `run_gov100_spiders.sh` | 政府名单前 100 家：按序运行 websearch/news/tech/recruitment/bidding |

### 5.3 数据脚本（`scripts/*.py`）

| 脚本 | 用途 |
|------|------|
| `integrated_crawl.py` | 集成爬取（清空关联表后采集 4 维度数据） |
| `run_deepseek_rating.py` | DeepSeek 批量评级写库 |
| `verify_results.py` | 最终结果模型验证（零模型规则校验 + LLM 判读） |
| `export_individual.py` | 导出 `data/reports/individual.csv`（最终交付物） |
| `import_csv_to_db.py` | CSV 导入数据库 |
| `import_gov_list_to_db.py` | 政府名单（前 100 家）导入 companies（status=raw） |
| `enrich_gov100_bizinfo.py` | 补全政府名单前 100 家工商字段（百度百科 API 等免费渠道） |
| `fetch_credit_codes.py` | 批量获取统一社会信用代码（必应 / 水滴信用 / 爱企查） |
| `fetch_biz_info.py` / `fetch_biz_info_v2.py` | 工商信息多渠道补全 |
| `supplement_tech.py` | 技术画像补强（cloud_provider / github_org / tech_blog） |
| `supplement_top3.py` | 指定 3 家企业的真实工商数据补全（一次性脚本） |
| `run_category5.py` / `rate_all_category5.py` | 5 号名录批量评级（支持 `--resume` 续跑、`--csv-only`、`--limit`） |
| `export_gov100_scored.py` | 导出政府名单前 100 家评分结果 |
| `export_sync.py` / `import_sync.py` | 多机数据同步：爬取机导出 CSV → git push → 汇聚机幂等导入 |
| `generate_potential_companies.py` | ⚠️ 遗留：生成 LLM 编造的 1~5_*.csv 示例名单，**勿作为正式底池** |

### 5.4 单独调用爬虫

```bash
cd crawler
scrapy crawl business        # 工商信息
scrapy crawl tech            # 技术画像
scrapy crawl recruitment      # 招聘
scrapy crawl news            # 新闻舆情（-a mode=incremental|full，-a company=企业名 调试单家）
scrapy crawl bidding         # 招投标
scrapy crawl websearch       # 聚合搜索
```

> spider 参数（`-a key=value`）：
> - `business`: `mode=incremental|full`、`keyword=<关键词>`
> - `tech` / `recruitment` / `websearch`: `mode=incremental|full`、`company=<企业名>`
> - `news`: `mode=incremental|full`、`company=<企业名>`、`levels=S,A`（按已有评级等级筛选，热点追踪用）
> - `bidding`: 仅 `keyword=<关键词>`（无 mode）
>
> `news` 传了 `levels` 时忽略 `mode`，只抓取该等级企业（同名企业有 deepseek 与 rules_engine 两条评级时取 deepseek）。

---

## 六、数据库表

`db/init.sql` 定义 8 张表（多数表带业务唯一约束，支撑多机同步的幂等 upsert）：

| 表 | 说明 | 唯一约束 |
|----|------|---------|
| `companies` | 企业主表（工商信息 + status 状态机） | `credit_code` |
| `tech_profiles` | 技术画像（技术栈/云厂商/AI 岗占比） | `company_id` |
| `recruitments` | 招聘信息 | `(company_id, position_title, source_name)` |
| `news_mentions` | 新闻舆情 | `(company_id, title, source_name)` |
| `bidding_records` | 招投标记录 | `(company_id, project_name, source_name)` |
| `ratings` | 评级结果（分项分 + 等级 + 话术/理由） | `(company_id, rated_by)` |
| `crawl_tasks` | 爬虫任务追踪（本地状态，不参与同步） | - |
| `rating_changelog` | 评级变更日志 | - |

---

## 七、企业底池

| 文件 | 说明 |
|------|------|
| `data/potential_companies/0_government_certified.csv` | **真实底池**：1063 家武汉经信局公示认定企业（数字化改造验收 549 / 人工智能 367 / 软件·工业互联网 86 / 智能工厂 59 / 其他 2） |
| `0_government_certified_500.csv` | 前 500 家（全部来自数字化改造验收批次），用于首批试运行 |
| `0_government_certified_100_scored.csv` | 前 100 家评分结果导出 |
| `README_government_lists.md` | 底池来源、名单构成与原始页面链接 |

> 仓库原有的 `1_~5_*.csv`（约 500 家）是**大模型生成的未核实名单**，与政府名单仅重合 21 家，
> 已从版本库移除。请一律以 `0_government_certified*` 作为真实底池。

---

## 八、测试

```bash
source .venv/bin/activate
python -m pytest tests/ -q                 # 全部用例
python -m pytest tests/ -v --tb=short      # 详细输出
python -m pytest tests/test_spiders/ -v    # 仅爬虫相关（离线：Item/Pipeline/Spider 名）
```

覆盖范围：规则引擎、DeepSeek 客户端、报告生成、数据管道、WebSearch 聚合、爬虫 Item/管道/注册名。
爬虫测试为**离线测试**（不依赖网络与数据库）。

---

## 九、文档索引

| 文档 | 内容 |
|------|------|
| `skills/rating-pipeline.skill.md` | **全链路运行手册**（脚本顺序 + 效率优化 + 复盘），日常首选 |
| `docs/Hermes交接Prompt.md` | 项目交接指南（环境搭建/修复/联调/上线步骤） |
| `docs/开发流程.md` | 分 Phase 分步开发指南（可作为 prompt 逐步执行） |
| `docs/多机数据同步方案.md` | 多机（爬取机 ↔ 汇聚机）数据同步方案 |
| `CLAUDE.md` | 项目速览（供 Agent 上下文使用） |

---

## 十、注意事项

1. `CLAUDE.md` 中的 `scripts/setup.sh` **不存在**，环境搭建请按本文第四节执行。
2. `docs/` 与 `skills/` 中的部分路径仍写着旧机器的 `/Users/kc/Desktop/E-InfoInsight-agent-codes`，
   本机实际路径为 `/Users/henry/Desktop/repository/E-InfoInsigth-agent-codes`。
3. `config/config.yaml` 的 `scoring.pass_threshold: 60` 与规则引擎实际使用的阈值
   （`scoring_rules.yaml` 的 `level_thresholds.B = 40`）**不一致**，以 `scoring_rules.yaml` 为准。
4. `.env` 含密钥且已被 `.gitignore` 忽略，**不要提交**；`.env.example` 中的 `kc` 用户需替换为本机 PG 用户。
5. `integrated_crawl.py` 执行时会**清空** news/tech/recruit/bidding 关联表，请勿与其他爬虫并行运行。
6. DeepSeek 评级会消耗 API 额度，批量运行前建议先用 `--limit N` 小样本验证。
7. 分支约定：远程 `origin/master`（线上）、`origin/test`（开发）；本地开发分支为 `main`。
8. ~~`engine/llm_client.py` 没有 CLI 入口~~ — **已修复**。
   原先 `daily_update.sh` / `full_scan.sh` / `hot_track.sh` 里的
   `python engine/llm_client.py --mode <x>` 只会打印一行提示就退出（`--mode` 被忽略），
   DeepSeek 评级步骤是空操作。
   现在 `llm_client.py` 已补齐 CLI（`--mode` / `--levels` / `--limit`），
   流程实现在 `engine.llm_client.run_batch_rating`，`scripts/run_deepseek_rating.py` 改为复用同一份实现。
9. ~~`hot_track.sh` 的 S/A 过滤未生效~~ — **已修复**。
   原先 `scrapy crawl news -a levels=S,A` 中的 `levels` 被 `**kwargs` 静默吞掉，
   且选企逻辑无法按评级等级筛选。
   现在 `NewsSpider` 新增 `levels` 参数（`_parse_levels` 解析 + 按 `rating_level` 走
   `JOIN LATERAL` 选企），`hot_track.sh` 的重新评级步骤也改为 `--levels S,A`，
   热点追踪链路（S/A 新闻 → S/A 重评 → S/A 报告）已闭环。
10. 新增 `levels` 相关离线测试：`tests/test_spiders/test_news_levels.py`、
   `tests/test_llm_client.py::TestParseLevels`（共 210 个用例，全绿）。

### 环境实测记录

- 解释器：`/Users/henry/.local/bin/python3.11`（uv 安装的 3.11.15）；系统 `python3` 为 3.9.6，不可用
- 数据库：`postgresql@18` (Homebrew)，服务名 `brew services start postgresql@18`
- `scrapy list` 实测输出：`bidding, business, news, recruitment, tech, websearch`
- `pytest tests/ -q` 实测：`210 passed`
- `python engine/llm_client.py --help` 实测：CLI 三个参数均可用
- 当前库内 220 家企业**没有 S/A 级**（deepseek: C 30 / D 76；rules_engine: B 6 / C 51 / D 163），
  因此 `--levels S,A` 会返回 0 家，属正常数据现状而非故障

