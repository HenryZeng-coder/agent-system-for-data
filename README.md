# 全国企业智能化转型评级系统 (E-InfoInsight-National)

<div align="center">
<img src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white" alt="Windows"/>
<img src="https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white" alt="macOS"/>
<img src="https://img.shields.io/badge/iOS-000000?logo=apple&logoColor=white" alt="iOS"/>
<img src="https://img.shields.io/badge/Android-3DDC84?logo=android&logoColor=white" alt="Android"/>
</div>

面向**全国范围**企业的智能化转型潜在客户评级系统：从公开渠道采集企业工商/技术/招聘/舆情/招投标
多维数据，先用**规则引擎**做 5 维度加权初筛，再由 **DeepSeek** 做深度评级，输出 S/A/B/C/D 等级、
需求标签与销售话术，形成可直接使用的销售线索清单。

本项目由「武汉IT企业智能评级系统」改造而来，**唯一的结构性差别是采集范围可配置**：
全国 / 按省 / 按市，通过一行配置切换，代码中不再存在任何写死的地域。

- 技术栈: Python 3.11 + Scrapy 2.11 + PostgreSQL + DeepSeek API
- 编排方式: Hermes Agent Skills (`skills/`) + 运维脚本 (`scripts/`)

---

## 一、区域配置（本项目最核心的改动）

所有地域相关行为统一由 `engine/region.py` 决定，配置在 `config/config.yaml`：

```yaml
region:
  scope: national        # national(全国) | province(按省) | city(按市)
  province: ""           # scope=province|city 时必填, 如 湖北
  city: ""               # scope=city 时必填, 如 武汉
  local_domains: []      # 可选: 本地行业/招投标站点域名
```

三种范围的行为差异：

| scope | 搜索词前缀 | 地域词 | 说明 |
|-------|-----------|--------|------|
| `national`（默认） | 无 | 无 | 搜索词就是企业名/行业词本身；不做地域过滤；企业名与地址正则不限地域 |
| `province` | 省名，如 `湖北` | `湖北`、`湖北省` | 搜索加省前缀，地址/企业名匹配锚定该省 |
| `city` | 市名，如 `武汉` | `武汉`、`武汉市`、`湖北`、`湖北省` | 等价于原武汉版行为 |

也可以不改编排文件，用环境变量临时覆盖（见 `crawler/cn_it_crawler/settings.py`）：

```bash
REGION_SCOPE=city REGION_PROVINCE=湖北 REGION_CITY=武汉 scrapy crawl news
```

对外接口（写新爬虫时**不要**写死地名，一律走这里）：

```python
from engine.region import Region

region = Region.from_config()
region.query("某某科技有限公司")     # 全国 → "某某科技有限公司"；市级 → "武汉 某某科技有限公司"
region.strip_local(name)            # 从企业全名剥离地域词（用于派生简称）
region.company_name_pattern()       # 企业名提取正则
region.address_pattern()            # 注册地址提取正则
region.looks_like_address(text)     # 地址有效性判断
region.bidding_keywords([...])      # 招投标关键词
region.is_local(text)               # 是否属于本范围（全国模式恒为 True）
```

---

## 二、目录结构

```
E-InfoInsight-National/
├── config/
│   ├── config.yaml           # region / 数据库 / DeepSeek / 爬虫 / 调度 / 报告
│   ├── scoring_rules.yaml    # 5 维度评分规则（评分模型唯一事实来源）
│   ├── industry_keywords.yaml
│   ├── known_tech.json.example   # 可选: 已知技术信息（复制为 known_tech.json 后生效）
│   └── stock_map.json.example    # 可选: 上市公司代码（复制为 stock_map.json 后生效）
├── db/
│   ├── init.sql              # 建表 DDL（8 张表 + 索引 + 多机同步唯一约束）
│   ├── seed.sql              # 测试种子（10 家虚构样例，仅用于打通流水线）
│   └── seed_real.sql         # 样例种子（10 家真实企业，仅名字，工商字段留空待爬）
├── crawler/
│   ├── scrapy.cfg
│   ├── cn_it_crawler/
│   │   ├── settings.py       # 5 级管道 + REGION_* 注入 + 项目根 sys.path
│   │   ├── items.py          # 6 个 Item
│   │   ├── middlewares.py
│   │   ├── spiders/          # business / tech / recruitment / news / bidding / websearch
│   │   └── pipelines/        # dedup(100)→filter(200)→clean(300)→validate(400)→standardize(500)
│   └── utils/                # 反爬: proxy_pool / ua_rotator / captcha_solver / anti_detect
├── engine/
│   ├── region.py             # ★ 区域口径（全国/省/市）
│   ├── rules_engine.py       # 5 维度加权评分（CLI: --mode incremental|full）
│   ├── llm_client.py         # DeepSeek 批量评级（CLI: --mode/--levels/--limit）
│   ├── report.py             # 日报 / 线索 CSV+Excel 导出（--mode daily|leads|notify）
│   ├── data_pipeline.py      # 非 Scrapy 场景的 5 级数据管道
│   ├── websearch.py          # 多引擎搜索聚合（百度/搜狗/必应/360/头条）
│   └── prompts/              # analysis_prompt.md + few_shot_examples.json
├── skills/                   # Hermes Skills: rating-pipeline / crawl / score / analyze / report
├── scripts/                  # 运维与数据脚本（见第五节）
├── tests/                    # pytest（210 用例）
├── data/
│   ├── potential_companies/  # 企业底池（需自己准备，见第七节）
│   ├── exports/  reports/  sync/
├── logs/
└── docs/                     # 交接说明 / 开发流程 / 多机同步方案
```

---

## 三、数据流

```
                 crawler(6 spiders)          rules_engine          llm_client            report
  companies ────────────────────────►  status='raw'
     ▲                                        │                      │                    │
     │                                        ▼                      ▼                    ▼
     └── 名单导入/工商补全               status='scored'  ──►  status='rated'  ──►  data/reports/*
                                          (规则初筛)          (DeepSeek 深度评级)    日报/线索/individual.csv
```

- `companies.status`: `raw → scored → rated`
- `ratings.rated_by`: `rules_engine` / `deepseek`（同一企业可同时存在两条）
- 规则引擎初筛达标线：`level_thresholds.B = 40`，B 级及以上送 DeepSeek 深度评级

---

## 四、快速开始

### 4.1 环境要求

| 组件 | 版本 |
|------|------|
| Python | 3.11+（系统 `python3` 若为 3.9 需另装） |
| PostgreSQL | 16+ |
| Playwright Chromium | 供 scrapy-playwright 使用 |

### 4.2 安装

```bash
cd /Users/henry/Desktop/E-InfoInsight-National

# 1. 虚拟环境（本机 3.11 解释器路径示例）
/Users/henry/.local/bin/python3.11 -m venv .venv
source .venv/bin/activate

# 2. 依赖
pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium

# 3. 数据库
brew services start postgresql@18        # 或 postgresql@16
createdb rating_system_national
psql -d rating_system_national -f db/init.sql
psql -d rating_system_national -f db/seed_real.sql   # 或 db/seed.sql（虚构样例）

# 4. 环境变量
cp .env.example .env
# 填 DEEPSEEK_API_KEY / DATABASE_URL / HERMES_WORKDIR
chmod +x scripts/*.sh
```

### 4.3 验证

```bash
psql -d rating_system_national -c "SELECT status, count(*) FROM companies GROUP BY status"
cd crawler && scrapy list && cd ..        # 期望 business tech recruitment news bidding websearch
python -c "from engine.region import Region; print(Region.from_config().describe())"
python -m pytest tests/ -q                # 期望 210 passed
```

---

## 五、常用命令

### 5.1 全链路

```bash
# 1) 导入企业底池
python scripts/import_company_pool.py --csv data/potential_companies/company_pool.csv

# 2) 集成爬取（4 维度；会先清空关联表，勿与其他爬虫并行）
python scripts/integrated_crawl.py > logs/run_$(date +%Y%m%d_%H%M%S).log 2>&1

# 3) 规则引擎评分
python engine/rules_engine.py --mode full

# 4) DeepSeek 深度评级（两个入口共用 engine.llm_client.run_batch_rating）
python engine/llm_client.py --mode full
python scripts/run_deepseek_rating.py full        # 位置参数 full|incremental|hot_track
#    追加: --levels S,A 只重评指定等级 | --limit N 小样本验证

# 5) 结果验证 / 导出 / 日报
python scripts/verify_results.py --limit 50
python scripts/export_individual.py
python engine/report.py --mode daily --date $(date +%Y-%m-%d)
```

### 5.2 运维脚本

| 脚本 | 用途 |
|------|------|
| `daily_update.sh` | 每日增量：增量爬取 → 评分 → DeepSeek → 日报 |
| `full_scan.sh` | 全量重跑：6 spider 全量 → 评分 → 评级 → 报告 |
| `hot_track.sh` | 热点追踪：S/A 级新闻 → S/A 重评（`--levels S,A`）→ 追踪报告 |
| `run_all_spiders.sh` | 按序运行 5 个 spider 采集 4 维数据 |

### 5.3 数据脚本

| 脚本 | 用途 |
|------|------|
| `import_company_pool.py` | 名单 CSV → companies（status=raw），`--csv/--limit` |
| `import_csv_to_db.py` | 带工商字段的 CSV → companies，`--csv` |
| `enrich_bizinfo.py` | 补全 raw 企业工商字段（百度百科 API 等免费渠道），`--limit` |
| `fetch_credit_codes.py` | 批量获取统一社会信用代码，`--csv/--out/--limit` |
| `fetch_biz_info.py` | 工商信息补全（百科 + 东财 F10 + 必应兜底），`--csv/--out/--limit` |
| `fetch_biz_info_v2.py` | 第二渠道：必应定位真实注册名 → 详情页提取信用代码，`--in/--out` |
| `supplement_tech.py` | 按 `config/known_tech.json` 回填 tech_profiles |
| `integrated_crawl.py` | 集成爬取（清空关联表后采集 4 维） |
| `incremental_crawl_and_score.py` | 增量爬取 + 评分 |
| `run_deepseek_rating.py` / `engine/llm_client.py` | DeepSeek 评级 |
| `verify_results.py` | 结果验证（规则校验 + 模型判读） |
| `export_individual.py` | 导出 `data/reports/individual.csv` |
| `export_sync.py` / `import_sync.py` | 多机数据同步（导出 CSV → git → 幂等导入） |

### 5.4 单独调用爬虫

```bash
cd crawler
scrapy crawl business        # 工商信息
scrapy crawl tech            # 技术画像
scrapy crawl recruitment     # 招聘
scrapy crawl news            # 新闻（-a mode=incremental|full，-a levels=S,A，-a company=企业名）
scrapy crawl bidding         # 招投标
scrapy crawl websearch       # 聚合搜索
```

---

## 六、评分模型

规则全部位于 `config/scoring_rules.yaml`，总分上限 100。地域不影响打分口径。

| 维度 | 上限 | 主要计分项 |
|------|-----|-----------|
| `tech_investment` 技术投入 | 30 | AI 岗位占比 ≥0.2 → 15；云厂商 5；GitHub 组织 5；技术博客 5；经营范围兜底 |
| `funding` 资金实力 | 25 | 融资阶段 B/C 15、A 10、D 5；注册资本 ≥1000 万 5；规模梯度 ≥5亿 8 / ≥1亿 5 / ≥5000万 3 |
| `transformation_intent` 转型意向 | 30 | 新闻关键词 5/个（上限 20）；数字化招投标 10；经营范围意图 5/5/3；跨维度加成 |
| `team_size` 团队规模 | 15 | 招聘岗位数 50→15 / 20→10 / 5→5；注册资本兜底 |
| `industry_match` 行业匹配 | 10 | 高匹配关键词 +2/个，低匹配 −1/个 |

等级阈值：`S ≥ 80`、`A ≥ 60`、`B ≥ 40`、`C ≥ 20`、`D < 20`。

---

## 七、企业底池

本仓库**不附带**任何企业名单。底池需来自真实公开渠道（各省市工信/经信部门公示的
数字化转型试点、智能工厂、人工智能应用服务商等认定名单），格式与获取方法见
`data/potential_companies/README.md`。

> 切勿用大模型生成企业名单——会引入大量不存在的公司，污染整个评级结果。

---

## 八、测试

```bash
source .venv/bin/activate
python -m pytest tests/ -q                 # 210 用例
python -m pytest tests/test_spiders/ -v    # 爬虫离线测试（Item/管道/名称/levels）
```

---

## 九、文档

| 文档 | 内容 |
|------|------|
| `skills/rating-pipeline.skill.md` | 全链路运行手册（脚本顺序 + 效率优化 + 复盘），日常首选 |
| `docs/Hermes交接Prompt.md` | 接手说明：环境、区域改法、流水线、注意事项 |
| `docs/开发流程.md` | 分 Phase 开发指南 |
| `docs/多机数据同步方案.md` | 多机同步方案 |
| `data/potential_companies/README.md` | 底池来源与格式 |
| `CLAUDE.md` | 项目速览（供 Agent 读取） |

---

## 十、已知问题与注意事项

1. **全国范围的数据缺失是本项目最大的现实制约。** 单城市采集时工商/招聘/舆情覆盖率较高，
   放大到全国后覆盖率显著下降，而规则引擎直接依赖这些字段（技术画像、招聘数、新闻命中），
   缺失会压低得分、使评级整体失真。**当前未做兜底策略**，属于已知待改进项。
   建议的改进方向：按省份分批采集、引入更多工商数据源、对缺失维度做置信度折扣而非按 0 计分。
2. `integrated_crawl.py` 执行时会清空 news/tech/recruit/bidding 关联表，不可与其他爬虫并行。
3. DeepSeek 评级按量计费，批量前先用 `--limit N` 小样本验证。
4. `.env` 含密钥，已被 `.gitignore` 忽略，不要提交。
5. `db/seed_real.sql` 中的企业**只有名称是真实的**，工商字段与信用代码留空待采集，
   不要当作已核实数据。
6. 从武汉版继承下来并已修复的问题：
   - `db/seed_real.sql` 原先用错列名 `procurement_type`（schema 实为 `project_type`），执行必报错；
   - `requirements.txt` 漏了 `beautifulsoup4`，而 `engine/websearch.py` 依赖它，
     干净环境下安装后新闻/招聘/招投标爬虫会直接 ImportError；
   - `engine/llm_client.py` 缺少 CLI 入口导致 `.sh` 脚本的评级步骤空转；
   - `news_spider` 的 `-a levels=S,A` 被静默忽略，热点追踪无法按等级筛企；
   - `crawler/cn_it_crawler/settings.py` 与 `scripts/integrated_crawl.py` 的 `.env` 路径多上溯了一层。
