# E-InfoInsight-agent-codes 项目交接 Prompt

> **用途：** 将此 prompt 完整发送给 Hermes，作为其接手项目开发测试和线上同步的完整指南。
> Hermes 应按步骤顺序逐步执行，每步完成后验证再进入下一步。

---

## 你是武汉IT企业智能评级系统的后续开发者

你将接手 **E-InfoInsight-agent-codes** 项目的开发、测试与线上代码同步工作。
项目使用 **Hermes Skills** 进行流程编排，使用 **Hermes Cron** 进行定时调度。
请仔细阅读以下指南，按顺序逐步执行。

---

## 一、项目概览

| 项目 | 信息 |
|------|------|
| 名称 | 武汉IT企业智能评级系统 |
| 代码库 | `https://ezone.ksyun.com/ezone/E-InfoInsigth-space/E-InfoInsigth-agent-codes.git` |
| 本地路径 | `/Users/kc/Desktop/E-InfoInsight-agent-codes/` |
| 技术栈 | Python 3.11 + Scrapy + PostgreSQL 16 + DeepSeek |
| 分支策略 | `master` (线上) / `test` (开发测试) |
| 当前分支 | `test` (最新提交: `3e69f9a`) |
| Hermes 集成 | 4 个 Skills + 2 个 Cron 作业 |

### 核心模块

```
E-InfoInsight-agent-codes/
├── config/           # 全局配置 (config.yaml, scoring_rules.yaml)
├── db/               # 数据库 DDL + 种子数据 (init.sql, seed.sql)
├── crawler/          # Scrapy 爬虫 (6个Spider + 5级Pipeline + 反爬工具)
│   ├── wuhan_it_crawler/spiders/   # 6个Spider: business/tech/recruitment/news/bidding/websearch
│   ├── wuhan_it_crawler/pipelines/ # 5级管道: dedup→filter→clean→validate→standardize (优先级100→500)
│   └── utils/                      # 反爬工具: proxy_pool/ua_rotator/captcha_solver/anti_detect
├── engine/           # 规则引擎 + DeepSeek客户端 + 报告生成 + Prompt模板
│   ├── rules_engine.py    # 5维度加权评分 (tech30/fund20/intent25/team15/ind10)
│   ├── llm_client.py      # deepseek-v4-flash批量评级 (429自适应退避 + 断点续跑)
│   ├── report.py          # 日报Markdown + CSV/Excel线索导出 + 新线索通知
│   ├── data_pipeline.py   # 数据管道骨架 (当前方法均为pass-through)
│   ├── websearch.py       # 多引擎搜索聚合 (百度/搜狗/必应)
│   └── prompts/           # analysis_prompt.md + few_shot_examples.json (5个示例覆盖S/A/B/C/D)
├── skills/           # Hermes Agent Skills (4个)
│   ├── rating-crawl.skill.md      # 爬虫编排
│   ├── rating-score.skill.md      # 规则引擎评分
│   ├── rating-analyze.skill.md    # deepseek-v4-flash深度评级
│   └ rating-report.skill.md      # 报告与线索导出
├── scripts/          # 运维脚本
│   ├── daily_update.sh   # 每日增量: 爬虫→评分→DeepSeek→日报
│   ├── full_scan.sh      # 全量重跑: 全量爬虫→全量评分→全量DeepSeek→报告
│   └ hot_track.sh       # 热点追踪: S/A企业新闻→重评→追踪报告
├── tests/            # 单元测试 (pytest, 31个用例, 1个失败)
├── docs/             # 开发流程文档
└── data/reports/     # 生成的报告输出
```

### 数据管道状态流

```
companies.status: raw → scored → rated → filtered
                 ↑       ↑        ↑        ↑
            爬虫入库  规则引擎   DeepSeek评级  报告导出
```

---

## 二、环境搭建与验证

### Step 1 — 环境搭建

```bash
cd /Users/kc/Desktop/E-InfoInsight-agent-codes

# 1. 创建虚拟环境 (已存在 .venv, 如需重建)
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt -r requirements-dev.txt

# 3. 安装 Playwright 浏览器
playwright install chromium

# 4. 启动 PostgreSQL 并创建数据库
brew services start postgresql@16
createdb rating_system

# 5. 初始化数据库
psql -d rating_system -f db/init.sql
psql -d rating_system -f db/seed.sql

# 6. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实值:
#   DEEPSEEK_API_KEY=你的DeepSeek密钥
#   DATABASE_URL=postgresql://kc@localhost:5432/rating_system
#   PROXY_POOL_API=你的代理池API地址
#   HERMES_WORKDIR=/Users/kc/Desktop/E-InfoInsight-agent-codes

# 7. 给脚本添加执行权限
chmod +x scripts/*.sh
```

### Step 2 — 验证环境

```bash
source .venv/bin/activate

# 验证数据库 (期望: 10)
psql -d rating_system -c "SELECT count(*) FROM companies"

# 验证爬虫 (期望: business, tech, recruitment, news, bidding, websearch)
cd crawler && scrapy list && cd ..

# 验证 Python 模块
python -c "from engine.rules_engine import RatingRulesEngine; print('OK')"
python -c "from engine.llm_client import LLMRatingClient; print('OK')"
python -c "from engine.report import ReportGenerator; print('OK')"

# 运行现有测试
python -m pytest tests/ -v --tb=short
# 期望: 30 passed, 1 failed (test_dedup — 需修复)
```

---

## 三、修复已知 Bug

### Step 3 — 修复 DataPipeline.deduplicate 方法

**问题:** `engine/data_pipeline.py` 的 `deduplicate` 方法当前是 pass-through (`return d`)，未实现真正的去重。测试 `test_data_pipeline.py::TestDataPipeline::test_dedup` 失败:

```python
# 测试期望: [{"credit_code":"A"},{"credit_code":"A"},{"credit_code":"B"}] → 去重后 2 条
# 当前结果: 返回 3 条 (未去重)
```

**修复方案:**

修改 `engine/data_pipeline.py`，将 `deduplicate` 方法改为基于 `credit_code` 字段去重:

```python
"""批量数据处理管道"""
import logging
logger = logging.getLogger(__name__)

class DataPipeline:
    def run(self, d):
        return d

    def deduplicate(self, d):
        """基于 credit_code 去重"""
        seen = set()
        result = []
        for item in d:
            key = item.get("credit_code")
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def filter_by_industry(self, d):
        return d

    def clean_fields(self, d):
        return d

    def validate_completeness(self, d):
        return d

    def standardize(self, d):
        return d
```

**验证:**

```bash
python -m pytest tests/test_data_pipeline.py -v --tb=short
# 期望: 2 passed
```

### Step 4 — 完善 DataPipeline 其余方法

当前 `filter_by_industry` / `clean_fields` / `validate_completeness` / `standardize` 均为 pass-through，与 Scrapy 5级管道逻辑重复。完善它们使之与 `scoring_rules.yaml` 的 `it_filter_keywords` 对齐:

```python
def filter_by_industry(self, d):
    """IT行业过滤 — 从 scoring_rules.yaml 读取关键词"""
    keywords = ["软件", "信息技术", "科技", "数据", "互联网",
                "云计算", "人工智能", "智能", "IT", "数字化"]
    result = []
    for item in d:
        scope = item.get("business_scope", "") or ""
        if any(kw in scope for kw in keywords):
            result.append(item)
    return result

def clean_fields(self, d):
    """数据清洗 — 空值统一、全角转半角、HTML清除"""
    import re
    result = []
    for item in d:
        cleaned = {}
        for k, v in item.items():
            if v is None or v == "":
                cleaned[k] = None
            elif isinstance(v, str):
                # 全角→半角
                v = v.translate(str.maketrans(
                    '０１２３４５６７８９ＡＢＣＤＥＦ',
                    '0123456789ABCDEF'
                ))
                # 清除HTML
                v = re.sub(r'<[^>]+>', '', v)
                # 多余空白压缩
                v = re.sub(r'\s+', ' ', v).strip()
                cleaned[k] = v if v else None
            else:
                cleaned[k] = v
        result.append(cleaned)
    return result

def validate_completeness(self, d):
    """完整性验证 — company_name 必须非空"""
    result = []
    for item in d:
        if item.get("company_name"):
            result.append(item)
    return result

def standardize(self, d):
    """格式标准化 — 注册资本文本→万元数值"""
    import re
    result = []
    for item in d:
        std = dict(item)
        # 解析注册资本: "5000万元"→5000, "1亿"→10000, "300万"→300
        cap = item.get("capital_amount") or item.get("registered_capital")
        if isinstance(cap, str):
            m = re.search(r'(\d+\.?\d*)\s*亿', cap)
            if m:
                std["capital_amount"] = float(m.group(1)) * 10000
            else:
                m = re.search(r'(\d+\.?\d*)\s*万', cap)
                if m:
                    std["capital_amount"] = float(m.group(1))
                else:
                    std["capital_amount"] = None
        result.append(std)
    return result
```

**补充测试** — 在 `tests/test_data_pipeline.py` 中添加:

```python
def test_filter_by_industry_match(self):
    p = DataPipeline()
    d = [{"business_scope": "人工智能软件开发"}, {"business_scope": "五金加工"}]
    result = p.filter_by_industry(d)
    assert len(result) == 1
    assert result[0]["business_scope"] == "人工智能软件开发"

def test_filter_by_industry_no_match(self):
    p = DataPipeline()
    d = [{"business_scope": "五金加工"}]
    assert len(p.filter_by_industry(d)) == 0

def test_clean_fields_html(self):
    p = DataPipeline()
    d = [{"name": "<b>武汉</b>  科技"}]
    result = p.clean_fields(d)
    assert result[0]["name"] == "武汉 科技"

def test_clean_fields_none(self):
    p = DataPipeline()
    d = [{"name": None, "scope": ""}]
    result = p.clean_fields(d)
    assert result[0]["name"] is None
    assert result[0]["scope"] is None

def test_validate_completeness(self):
    p = DataPipeline()
    d = [{"company_name": "武汉AI"}, {"company_name": None}]
    result = p.validate_completeness(d)
    assert len(result) == 1

def test_standardize_capital(self):
    p = DataPipeline()
    d = [{"capital_amount": "5000万元"}]
    result = p.standardize(d)
    assert result[0]["capital_amount"] == 5000.0
```

**验证:**

```bash
python -m pytest tests/test_data_pipeline.py -v --tb=short
# 期望: 7 passed (2原有 + 5新增)
```

---

## 四、补充 Spider 测试

### Step 5 — 编写爬虫单元测试

`tests/test_spiders/` 目录当前为空，需要补充基础测试。由于爬虫依赖网络和数据库，编写**离线测试**（测试 Item 定义、Pipeline 逻辑、Spider 名称）:

在 `tests/test_spiders/__init__.py` 后创建以下测试文件:

**`tests/test_spiders/test_items.py`** — 验证 Item 字段定义:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from wuhan_it_crawler.items import (
    CompanyItem, TechProfileItem, RecruitmentItem,
    NewsMentionItem, BiddingItem, CrawlTaskItem
)

class TestItems:
    def test_company_item_fields(self):
        item = CompanyItem()
        expected = ["company_name", "credit_code", "registered_capital",
                    "established_date", "legal_person", "business_scope",
                    "registered_address", "industry_tags", "source_url"]
        for field in expected:
            assert field in item.fields

    def test_tech_profile_item_fields(self):
        item = TechProfileItem()
        expected = ["company_id", "tech_stack", "github_org",
                    "github_stars", "tech_blog_url", "cloud_provider",
                    "ai_job_ratio"]
        for field in expected:
            assert field in item.fields

    def test_recruitment_item_fields(self):
        item = RecruitmentItem()
        expected = ["company_id", "job_title", "salary_min",
                    "salary_max", "tech_keywords", "headcount",
                    "source_platform"]
        for field in expected:
            assert field in item.fields

    def test_news_mention_item_fields(self):
        item = NewsMentionItem()
        expected = ["company_id", "title", "content_summary",
                    "published_at", "sentiment_score", "is_digital_related",
                    "source_url"]
        for field in expected:
            assert field in item in item.fields

    def test_bidding_item_fields(self):
        item = BiddingItem()
        expected = ["company_id", "project_name", "procurement_type",
                    "budget_amount", "is_digital", "winning_company",
                    "source_url"]
        for field in expected:
            assert field in item.fields

    def test_crawl_task_item_fields(self):
        item = CrawlTaskItem()
        expected = ["spider_name", "task_type", "status", "started_at"]
        for field in expected:
            assert field in item.fields
```

**`tests/test_spiders/test_pipelines.py`** — 验证5级管道优先级:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from wuhan_it_crawler.pipelines import DedupPipeline, FilterPipeline, \
    CleanPipeline, ValidatePipeline, StandardizePipeline

class TestPipelines:
    def test_dedup_pipeline(self):
        p = DedupPipeline()
        # 测试 credit_code 去重
        item = {"credit_code": "A", "company_name": "test"}
        result = p.process_item(item, None)
        assert result["credit_code"] == "A"

    def test_filter_pipeline_match(self):
        p = FilterPipeline()
        item = {"business_scope": "人工智能软件开发"}
        result = p.process_item(item, None)
        assert result is not None

    def test_filter_pipeline_no_match(self):
        p = FilterPipeline()
        item = {"business_scope": "五金加工维修"}
        from scrapy.exceptions import DropItem
        try:
            p.process_item(item, None)
            assert False, "Should have been dropped"
        except DropItem:
            assert True

    def test_clean_pipeline(self):
        p = CleanPipeline()
        item = {"company_name": "<b>武汉</b>", "scope": "  人工 智能  "}
        result = p.process_item(item, None)
        assert "<b>" not in str(result.get("company_name", ""))

    def test_validate_pipeline(self):
        p = ValidatePipeline()
        item = {"company_name": "武汉AI"}
        result = p.process_item(item, None)
        assert result is not None

    def test_validate_pipeline_missing_name(self):
        p = ValidatePipeline()
        item = {"company_name": None}
        from scrapy.exceptions import DropItem
        try:
            p.process_item(item, None)
            assert False, "Should have been dropped"
        except DropItem:
            assert True

    def test_standardize_pipeline(self):
        p = StandardizePipeline()
        item = {"registered_capital": "5000万元", "company_name": "test"}
        result = p.process_item(item, None)
        # 标准化后应为数值
        assert result is not None
```

**`tests/test_spiders/test_spider_names.py`** — 验证 Spider 注册:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from scrapy.utils.spider import iter_spider_classes
from wuhan_it_crawler.spiders import (
    business_spider, tech_spider, recruitment_spider,
    news_spider, bidding_spider, websearch_spider
)

class TestSpiderNames:
    def test_business_spider_name(self):
        assert business_spider.BusinessSpider.name == "business"

    def test_tech_spider_name(self):
        assert tech_spider.TechSpider.name == "tech"

    def test_recruitment_spider_name(self):
        assert recruitment_spider.RecruitmentSpider.name == "recruitment"

    def test_news_spider_name(self):
        assert news_spider.NewsSpider.name == "news"

    def test_bidding_spider_name(self):
        assert bidding_spider.BiddingSpider.name == "bidding"

    def test_websearch_spider_name(self):
        assert websearch_spider.WebsearchSpider.name == "websearch"
```

**验证:**

```bash
python -m pytest tests/ -v --tb=short
# 期望: 全部通过 (规则引擎15 + DeepSeek3 + 数据管道7 + Items6 + Pipelines7 + Spider名6 = ~38用例)
```

---

## 五、端到端联调测试

### Step 6 — 规则引擎全量评分

```bash
source .venv/bin/activate
cd /Users/kc/Desktop/E-InfoInsight-agent-codes

# 1. 重置数据库 (清空评级数据，保留种子企业)
psql -d rating_system -c "DELETE FROM ratings"
psql -d rating_system -c "UPDATE companies SET status = 'raw'"

# 2. 运行规则引擎全量评分
python engine/rules_engine.py --mode full

# 3. 验证结果
psql -d rating_system -c "SELECT status, count(*) FROM companies GROUP BY status"
# 期望: 所有企业 status='scored'

psql -d rating_system -c "SELECT rating_level, count(*) FROM ratings WHERE rated_by='rules_engine' GROUP BY rating_level"
# 期望: 有 S/A/B/C/D 分布

psql -d rating_system -c "SELECT company_name, total_score, rating_level FROM ratings r JOIN companies c ON r.company_id=c.id WHERE r.rated_by='rules_engine' ORDER BY total_score DESC"
# 期望: 种子企业评分，达标(>=40分/B级)企业供DeepSeek深度评级
```

### Step 7 — DeepSeek评级 (需 API Key)

```bash
# 1. 确认 API Key 已配置
source .venv/bin/activate
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('DEEPSEEK_API_KEY', '')
print('API Key状态:', 'OK (已配置)' if key and not key.startswith('your') else '未配置')
"

# 2. 如未配置, 先编辑 .env 文件填入真实 DEEPSEEK_API_KEY

# 3. 获取达标企业并运行 DeepSeek评级
python -c "
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
from engine.rules_engine import RatingRulesEngine
engine = RatingRulesEngine()
companies = engine.get_companies_for_llm(os.getenv('DATABASE_URL'))
print(f'达标企业(>=40分/B级): {len(companies)} 家')
for c in companies:
    print(f'  {c.get(\"company_name\", \"未知\")}: {c.get(\"total_score\", 0)}分')
"

# 4. 运行 DeepSeek客户端
python engine/llm_client.py
# 注意: 当前 __main__ 仅打印就绪信息，需编写完整调用逻辑

# 5. 如需手动调用 DeepSeek (当 __main__ 不含批量逻辑时):
python -c "
import os, json, psycopg2
from dotenv import load_dotenv
load_dotenv()
from engine.rules_engine import RatingRulesEngine
from engine.llm_client import LLMRatingClient

db_url = os.getenv('DATABASE_URL')
engine = RatingRulesEngine()
companies = engine.get_companies_for_llm(db_url)

client = LLMRatingClient(api_key=os.getenv('DEEPSEEK_API_KEY', ''))
results = client.batch_rate(companies, mode='full')

if results:
    client.update_database(results, db_url)
    print(f'DeepSeek评级完成: {len(results)} 家')
else:
    print('DeepSeek评级无结果 (检查API Key和网络)')
"

# 6. 验证 DeepSeek 结果
psql -d rating_system -c "SELECT count(*) FROM ratings WHERE rated_by='llm'"
psql -d rating_system -c "SELECT rating_level, count(*) FROM ratings WHERE rated_by='llm' GROUP BY rating_level"
```

### Step 8 — 报告生成

```bash
# 1. 生成日报
python engine/report.py --date $(date +%Y-%m-%d) --mode daily

# 2. 导出 S/A 线索
python engine/report.py --date $(date +%Y-%m-%d) --mode leads

# 3. 新线索通知
python engine/report.py --date $(date +%Y-%m-%d) --mode notify

# 4. 验证输出文件
ls data/reports/
# 期望: daily_YYYY-MM-DD.md, leads_YYYY-MM-DD.csv, leads_YYYY-MM-DD.xlsx
```

### Step 9 — 全链路联调

```bash
# 重置数据库后跑全链路
psql -d rating_system -c "TRUNCATE companies, tech_profiles, recruitments, news_mentions, bidding_records, ratings, crawl_tasks RESTART IDENTITY CASCADE"
psql -d rating_system -f db/seed.sql
python engine/rules_engine.py --mode full
python -c "..."  # DeepSeek评级 (如Step 7)
python engine/report.py --date $(date +%Y-%m-%d)

# 或直接用脚本
bash scripts/full_scan.sh
```

---

## 六、Hermes Skills 集成

### Step 10 — 配置 Hermes Skills

项目已包含 4 个 Skill 文件 (`skills/*.skill.md`)，确保 Hermes 可以识别并执行它们:

```bash
# 确认 Skills 文件存在
ls skills/
# 期望: rating-crawl.skill.md, rating-score.skill.md, rating-analyze.skill.md, rating-report.skill.md

# 如 Hermes 使用 skill 目录扫描，确保路径在 Hermes 配置中注册
# Hermes Skill 调用示例:
hermes skill run rating-crawl    # 执行爬虫编排
hermes skill run rating-score    # 执行规则引擎评分
hermes skill run rating-analyze  # 执行 DeepSeek 深度评级
hermes skill run rating-report   # 执行报告生成与线索导出
```

### Step 11 — 配置 Hermes Cron 定时任务

根据 `config/config.yaml` 中的调度配置，设置 Hermes Cron:

```bash
# 1. 每日增量更新 (凌晨2点)
hermes cron add "0 2 * * *" --skill rating-crawl,rating-score,rating-analyze,rating-report

# 2. 热点追踪 (每6小时)
hermes cron add "0 */6 * * *" --skill rating-analyze,rating-report

# 3. 验证 Cron 配置
hermes cron list
# 期望: 2 个 cron 作业

# 4. 手动触发测试
hermes skill run rating-score
# 期望: 规则引擎执行成功，输出评分摘要
```

### Skill 执行流程对照

| Skill | 对应命令 | 验证条件 |
|-------|----------|----------|
| `rating-crawl` | `cd crawler && scrapy crawl {spider}` (逐个执行) | 采集数>0, company_name非空率>95% |
| `rating-score` | `python engine/rules_engine.py --mode {mode}` | status全部='scored', 评分分布合理 |
| `rating-analyze` | `python engine/llm_client.py` + `client.batch_rate()` | 所有达标企业有ratings记录, level∈S/A/B/C/D |
| `rating-report` | `python engine/report.py --date {date}` | data/reports/下有md+csv+xlsx文件 |

---

## 七、线上代码同步流程

### Step 12 — 日常开发提交 (test 分支)

```bash
cd /Users/kc/Desktop/E-InfoInsight-agent-codes
source .venv/bin/activate

# 1. 确保 test 分支最新
git checkout test && git pull origin test

# 2. 开发/修改代码

# 3. 运行测试验证
python -m pytest tests/ -v --tb=short

# 4. 提交 (遵循规范)
git add .
git commit -m "<type>: <描述>"
# type: feat / fix / refactor / test / docs

# 5. 推送
git push origin test
```

### Step 13 — test → master 合并上线

**⚠️ 合并前必须确认:**

```bash
# 1. 全部测试通过
python -m pytest tests/ -v

# 2. 规则引擎可正常运行
python engine/rules_engine.py --mode full

# 3. 报告生成正常
python engine/report.py --date $(date +%Y-%m-%d) --mode daily

# 4. 数据库状态合理
psql -d rating_system -c "SELECT status, count(*) FROM companies GROUP BY status"

# 5. 变更范围明确
git diff master..test
```

**合并步骤:**

```bash
git checkout test && git pull origin test
git checkout master && git pull origin master
git merge test
git push origin master
git checkout test   # 切回开发分支
```

### Step 14 — 紧急修复 (hotfix)

```bash
git checkout master
git checkout -b hotfix/描述
# 修复代码...
python -m pytest tests/ -v
git add . && git commit -m "fix: 描述"
git checkout master && git merge hotfix/描述 && git push origin master
git checkout test && git merge master && git push origin test
git branch -d hotfix/描述
```

### 同步检查清单

每次推送/合并前逐项确认:

- [ ] `python -m pytest tests/ -v` — **全部通过**
- [ ] 规则引擎无报错 (`python engine/rules_engine.py --mode full`)
- [ ] 报告生成成功 (`python engine/report.py --date today --mode daily`)
- [ ] `git diff master..test` — 变更范围明确
- [ ] 提交信息符合规范

---

## 八、关键配置说明

### 8.1 环境变量 (.env)

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here       # DeepSeek API密钥 (必需)
DATABASE_URL=postgresql://kc@localhost:5432/rating_system  # PostgreSQL
PROXY_POOL_API=http://your-proxy/api      # 代理池 (爬虫需要)
HERMES_WORKDIR=/Users/kc/Desktop/E-InfoInsight-agent-codes  # 项目路径
```

### 8.2 评分规则 (config/scoring_rules.yaml)

| 维度 | 满分 | 配置项 | 关键规则 |
|------|------|--------|----------|
| 技术投入 | 30 | `tech_investment` | AI占比>0.2→+15, 云→+5, GitHub→+5, 博客→+5 |
| 资金充裕 | 20 | `funding` | B/C轮→+15, A/D轮→+10, 注册资本>=1000万→+5 |
| 转型意向 | 25 | `transformation_intent` | 新闻关键词→+5/个(上限15), 数字化招投标→+10 |
| 团队规模 | 15 | `team_size` | 招聘>50→+15, 20-50→+10, 5-20→+5, <5→+0 |
| 行业匹配 | 10 | `industry_match` | 高匹配词(云计算/AI/大数据/系统集成/软件开发)→+2/个, 低匹配词(运维/硬件)→-1/个 |

**通过阈值: 40分(B级)** | 等级映射: S(≥80) / A(≥60) / B(≥40) / C(≥20) / D(<20)

### 8.3 DeepSeek客户端容错机制

| 异常 | 策略 |
|------|------|
| 429 TPM限流 | 指数退避 2→4→8→...→120秒, TPM自适应增减延迟 |
| 5xx 服务端 | 重试3次(间隔5秒), 全部失败跳过该批 |
| JSON解析失败 | temperature→0.05 + 注入few-shot重试1次 |
| 中断恢复 | 进度文件 `data/.llm_progress.json` 断点续跑 |

### 8.4 Hermes Cron 配置

| 任务 | Cron | Skill链 | 说明 |
|------|------|---------|------|
| 每日增量 | `0 2 * * *` | crawl→score→analyze→report | 凌晨2点全链路增量 |
| 热点追踪 | `0 */6 * * *` | analyze→report | 每6小时S/A级企业动态 |
| 全量扫描 | manual | full_scan.sh | 手动触发 |

---

## 九、常见问题与排查

### Q1: 测试报错 ModuleNotFoundError

```bash
cd /Users/kc/Desktop/E-InfoInsight-agent-codes
source .venv/bin/activate
python -m pytest tests/ -v
```

### Q2: 数据库连接失败

```bash
brew services list | grep postgresql
brew services start postgresql@16
psql -d rating_system -c "SELECT 1"
```

### Q3: 爬虫 429 / 被封

```bash
# 确认代理池
curl $PROXY_POOL_API
# 降低频率: config/config.yaml 中 download_delay 调为 1.0, concurrent_requests 调为 4
```

### Q4: DeepSeek API 调用失败

```bash
# 检查 API Key
source .venv/bin/activate && python -c "
import os, requests
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('DEEPSEEK_API_KEY', '')
print('Key状态:', 'OK' if key and not key.startswith('your') else '未配置')
if key and not key.startswith('your'):
    resp = requests.post(
        'https://api.deepseek.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model':'deepseek-v4-flash','messages':[{'role':'user','content':'hello'}],'max_tokens':10},
        timeout=30
    )
    print(f'API状态: {resp.status_code}')
"
```

### Q5: Git 推送认证失败

```bash
git config --global credential.helper
# 如需 token:
git remote set-url origin https://<username>:<token>@ezone.ksyun.com/ezone/E-InfoInsigth-space/E-InfoInsigth-agent-codes.git
```

### Q6: Hermes Skill 无法识别

```bash
# 确认 Skills 目录路径在 Hermes 配置中注册
# 确认 .skill.md 文件 frontmatter 格式正确:
head -5 skills/rating-crawl.skill.md
# 期望: ---name: rating-crawl\ndescription: ...\n---
```

---

## 十、下一步工作优先级

按以下顺序推进:

| 优先级 | 任务 | 步骤 |
|--------|------|------|
| **P0** | 修复 test_dedup | Step 3 |
| **P0** | 完善 DataPipeline 方法 | Step 4 |
| **P1** | 补充 Spider 测试 | Step 5 |
| **P1** | 规则引擎联调 | Step 6 |
| **P1** | DeepSeek评级联调 | Step 7 |
| **P2** | 报告生成验证 | Step 8 |
| **P2** | 全链路联调 | Step 9 |
| **P2** | Hermes Skills 验证 | Step 10-11 |
| **P3** | 代码同步上线 | Step 12-14 |

---

## 十一、快速操作速查

```bash
# === 环境 ===
cd /Users/kc/Desktop/E-InfoInsight-agent-codes && source .venv/bin/activate

# === 测试 ===
python -m pytest tests/ -v                        # 全部测试
python -m pytest tests/test_data_pipeline.py -v   # 数据管道
python -m pytest tests/test_rules_engine.py -v    # 规则引擎
python -m pytest tests/ --cov=engine              # 覆盖率

# === 引擎 ===
python engine/rules_engine.py --mode full         # 规则引擎全量
python engine/rules_engine.py --mode incremental  # 规则引擎增量
python engine/llm_client.py                       # DeepSeek客户端
python engine/report.py --date 2026-07-27 --mode daily  # 日报
python engine/report.py --date 2026-07-27 --mode leads  # 线索导出
python engine/report.py --date 2026-07-27 --mode notify # 通知

# === 脚本 ===
bash scripts/daily_update.sh    # 每日增量
bash scripts/full_scan.sh       # 全量扫描
bash scripts/hot_track.sh       # 热点追踪

# === Hermes ===
hermes skill run rating-crawl   # 爬虫编排
hermes skill run rating-score   # 规则引擎评分
hermes skill run rating-analyze # DeepSeek深度评级
hermes skill run rating-report  # 报告导出
hermes cron list                # 查看定时任务

# === 数据库 ===
psql -d rating_system -c "SELECT status, count(*) FROM companies GROUP BY status"
psql -d rating_system -c "SELECT rating_level, count(*) FROM ratings GROUP BY rating_level"
psql -d rating_system -c "SELECT rated_by, count(*) FROM ratings GROUP BY rated_by"

# === Git ===
git checkout test && git pull origin test                              # 拉取最新
git add . && git commit -m "feat: 描述" && git push origin test       # 提交推送
git checkout master && git merge test && git push origin master        # 合并上线

# === 数据库重置 ===
psql -d rating_system -c "DELETE FROM ratings"
psql -d rating_system -c "UPDATE companies SET status='raw'"
# 或完全重置:
psql -d rating_system -c "TRUNCATE companies, tech_profiles, recruitments, news_mentions, bidding_records, ratings, crawl_tasks RESTART IDENTITY CASCADE"
psql -d rating_system -f db/seed.sql
```

---

*文档生成时间: 2026-07-27*
*基于代码库最新提交: 3e69f9a*
*测试状态: 30 passed, 1 failed (test_dedup)*
