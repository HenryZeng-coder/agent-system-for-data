# 端到端测试报告 — 2026-08-06

> 依据 `docs/Hermes交接Prompt.md` 完整执行, 数据单独导出至 `data/reports/e2e_test_data_2026-08-06.csv`

## 一、环境

| 项目 | 状态 |
|------|------|
| Python | 3.11.15 (.venv) |
| 依赖 | requirements.txt + requirements-dev.txt 安装成功 |
| PostgreSQL | 本地 rating_system 库 (45家企业种子+爬虫数据) |
| 爬虫 | 6个Spider注册正常 (business/tech/recruitment/news/bidding/websearch) |
| 模块导入 | rules_engine / llm_client / report / data_pipeline 全部 OK |
| DeepSeek API | deepseek-v4-flash 连通, HTTP 200 |

## 二、单元测试

```
166 passed in 0.62s   (原文档记录: 30 passed, 1 failed)
```

新增修复:
- `engine/rules_engine.py::_score_to_level` 改为 @staticmethod — 修复 5 个
  TestScoreToLevel 失败 (类调用 RatingRulesEngine._score_to_level(85) 报缺参)

## 三、规则引擎全量评分 (Step 6)

```
评分完成: 总计45家, 通过1家, 未通过44家
```

| rating_level | 数量 |
|--------------|------|
| B | 1 |
| C | 5 |
| D | 39 |

修复的 schema 问题:
- `companies.funding_stage` 列缺失 → ALTER TABLE 补充 + 同步 db/init.sql
- `ratings` 缺 (company_id, rated_by) 唯一约束 (ON CONFLICT 需要) → 补充 + 同步 init.sql
- `ratings.rated_by` 默认值 'glm' 过时 → 改为 'rules_engine'

## 四、DeepSeek 深度评级 (Step 7)

达标企业 (≥40分): 1 家 — 烽火通信科技股份有限公司 (规则引擎 44分/B)

DeepSeek 评级结果:

| company_id | 企业 | LLM评分 | 等级 | demand_tags |
|-----------|------|---------|------|-------------|
| 2 | 烽火通信科技股份有限公司 | 54 | C | 智能制造, 数据中台, 供应链数字化 |

修复的 llm_client 问题 (4处):
1. `get_companies_for_llm` 返回 `id` 但 client 需要 `company_id` → 补映射
2. deepseek-v4-flash 为推理模型, 默认 max_tokens=500 被推理消耗导致 content 为空
   → 改为 4000 + response_format=json_object + timeout 120s
3. `update_database` 写 `created_at` (表中无此列) → 改为 `rated_at`
4. demand_tags 以 JSON 字符串写入 TEXT[] 列报 malformed array → 改传 Python list

## 五、报告生成 (Step 8)

| 输出文件 | 状态 |
|----------|------|
| data/reports/daily_2026-08-06.md | 已生成 |
| data/reports/all_rated_companies.csv | 已导出 (合并历史) |
| data/reports/all_rated_companies.xlsx | 已导出 |
| notify | 今日无新 S/A 级线索 |

## 六、测试数据 CSV (本次交付)

**文件: `data/reports/e2e_test_data_2026-08-06.csv`** (45行 × 22列, UTF-8 BOM)

列说明:
- 企业基础: id, company_name, credit_code, capital_amount, established_date, business_scope, status, funding_stage
- 规则引擎: re_score, re_level, tech_score, funding_score, intent_score, team_score, industry_score, re_rated_at
- DeepSeek: llm_score, llm_level, demand_tags, sales_pitch, reasoning, llm_rated_at

## 七、数据库最终状态

```
status 分布: rated=1, scored=44
ratings 分布: rules_engine B×1/C×5/D×39, deepseek C×1
```

## 八、代码变更清单

```
M db/init.sql            — 补 funding_stage 列 + ratings 唯一约束 + rated_by 默认值
M engine/rules_engine.py — _score_to_level 静态化 + get_companies_for_llm 补 company_id
M engine/llm_client.py   — max_tokens 4000 + response_format json_object + timeout 120
                          + rated_at 列修正 + demand_tags 列表适配
M data/reports/all_rated_companies.{csv,xlsx} — 本次线索导出
```
