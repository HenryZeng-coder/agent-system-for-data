# 项目交接 / 接手开发说明

> 面向接手本项目的开发者或 AI Agent。建议按顺序阅读，先跑通环境再改代码。

## 一、项目定位

**全国企业智能化转型评级系统** —— 从公开渠道采集企业多维信息，
先由规则引擎做 5 维度加权初筛，再由 DeepSeek 深度评级，
产出 S/A/B/C/D 等级、需求标签与销售话术，形成销售线索清单。

与「武汉版」的唯一结构性差别是 **采集范围可配置**（全国 / 省 / 市），
通过 `config/config.yaml` 的 `region` 段切换，代码里不再有任何写死的地域。

## 二、环境搭建

```bash
cd /Users/henry/Desktop/E-InfoInsight-National

# 1. Python 3.11+ (系统 python3 若是 3.9 不可用)
python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium

# 2. PostgreSQL
brew services start postgresql@18        # 或 postgresql@16
createdb rating_system_national

# 3. 建表 + 样例数据
psql -d rating_system_national -f db/init.sql
psql -d rating_system_national -f db/seed_real.sql

# 4. 环境变量
cp .env.example .env
# 填 DEEPSEEK_API_KEY / DATABASE_URL / HERMES_WORKDIR
```

验收：

```bash
psql -d rating_system_national -c "SELECT count(*) FROM companies"   # 期望 10
cd crawler && scrapy list && cd ..    # 期望 6 个 spider
python -m pytest tests/ -q            # 期望全绿
```

## 三、核心改法：区域配置

`engine/region.py` 是唯一的地域口径来源。spider 与脚本都通过它拿搜索词：

```python
from engine.region import Region

region = Region.from_config()      # 读 config.yaml
region.query("某某科技有限公司")    # 全国 → "某某科技有限公司"
                                   # 市级 → "武汉 某某科技有限公司"
region.strip_local(name)           # 从企业全名剥离地域词
region.company_name_pattern()      # 企业名提取正则（全国模式不限地域）
region.bidding_keywords([...])     # 招投标关键词（全国模式为纯行业词）
```

新增爬虫时不要写死地名，一律走 `region.query(...)`。切换范围只改配置：

```yaml
region:
  scope: city      # national | province | city
  province: 湖北
  city: 武汉
```

## 四、流水线

```
companies(status=raw) → 爬取4维 → 规则评分(scored) → DeepSeek评级(rated) → 报告/individual.csv
```

顺序与脚本清单见 `skills/rating-pipeline.skill.md`（运行手册）与 README。

## 五、注意事项

- `integrated_crawl.py` 会**清空** news/tech/recruit/bidding 关联表，不可与其他爬虫并行。
- DeepSeek 评级按量计费，批量前先用 `--limit N` 小样本验证。
- `.env` 含密钥，已在 `.gitignore` 中，不要提交。
- 企业底池必须来自真实公开名单；**不要**用大模型生成企业名单（会引入不存在的公司），
  详见 `data/potential_companies/README.md`。
- 数据缺失（全国范围下工商/招聘/舆情覆盖度低于单城市）会直接影响规则引擎得分，
  当前未做兜底策略——这是已知待改进项。
