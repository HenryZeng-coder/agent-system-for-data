# 5号名录(智能制造) 续跑运行总结 — 2026-08-19

## 运行信息
- 命令: `python scripts/run_category5.py --resume --csv-only`
- 日志: `logs/run_category5_smart100_20260819_102515.log`
- 起始: 2026-08-19 10:25:16
- 结束: 2026-08-19 11:05:10 (总耗时 ~40分钟)
- 处理企业: 96 家 (5号名录 raw 企业)

## 采集结果
| 维度 | 数量 | 说明 |
|------|------|------|
| 新闻舆情 | 974 条 | 平均 ~10条/家，百度/必应正常，搜狗偶发反爬降级 |
| 技术画像 | 96 家 | 全覆盖；GitHub 全空(SSL被断)，已由 KNOWN_TECH 逻辑兜底 |
| 招聘信息 | 408 条 | 搜索推断生成 |
| 招投标 | 24 条 | 部分企业无中标记录 |

## 评分与评级
- 规则引擎评分: 通过 1 家 (≥40分/B级达标), 未通过 95 家
- DeepSeek 深度评级: 1 家 → C级
- 达标率低原因: 智能制造名录多为传统装备制造企业(机器人/数控/电气),
  经营范围缺乏 AI/软件/云 等 IT 维度关键词，技术投入/行业匹配得分普遍偏低

## 数据库状态
- companies: rated 13 / scored 105 / raw 92 (raw 为其他名录待处理)
- ratings(deepseek): B=7, C=6

## 输出
- `data/potential_companies/5_smart_manufacturing_scored.csv` — 96家, 18列
  (company_name, credit_code, registered_capital, business_scope, industry_tags,
   registered_address, funding_stage, total_score, rating_level, tech_score,
   funding_score, intent_score, team_score, industry_score, demand_tags,
   sales_pitch, reasoning, crawl_time)

## 备注
- 运行前曾启动全量 --resume (188家)，发现与 --csv-only 并行冲突后终止，
  改用 --csv-only 限定本名录
- 429 限流: 未出现 (DeepSeek 阶段仅1家，未触发限流；llm_client 已内置
  指数退避+断点续跑作为兜底)
- git: 结果已提交 (115aeea)
