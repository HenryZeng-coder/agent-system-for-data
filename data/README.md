# data/ 说明

本目录下与评级流水线**无关**的文件（可选的人工调研模板）：

| 文件 | 用途 |
|------|------|
| `companies.csv` | 企业基础信息调研表（类型/行业/注册资本/员工数/成立年/官网） |
| `rnd_staff.csv` | 研发人员与研发投入调研表 |
| `strategy_plan.csv` | 企业战略规划调研表（用于判断转型意向强度） |
| `transformation_investment.csv` | 智能化改造投入调研表 |
| `transformation_results.csv` | 改造成效调研表 |

这几个 CSV 目前**只是模板**（仅表头、无数据），供人工整理企业深度资料时使用，
流水线与评分引擎不读取它们。若要启用，需自己在脚本中接入。

流水线真正使用的目录：

| 目录 | 用途 |
|------|------|
| `potential_companies/` | 企业底池名单与补全结果（见该目录 README） |
| `exports/` | 数据表全量 CSV 导出 |
| `reports/` | 日报 / 线索 / individual.csv / 验证报告 |
| `sync/` | 多机同步中间 CSV（`scripts/export_sync.py` / `import_sync.py`） |
