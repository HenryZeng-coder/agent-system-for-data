---
name: rating-pipeline
description: Use when 需要执行武汉IT企业评级系统全链路（全量/增量/热点爬取→评分→DeepSeek评级→模型验证→报告→多机同步），或排查爬取效率。按脚本调用顺序执行，每次运行写日志并复盘优化。
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [crawler, pipeline, rating, scrapy, efficiency]
    related_skills: [rating-crawl, rating-score, rating-analyze, rating-report]
---

# 全链路爬取流水线（脚本调用顺序）

## Overview

武汉IT企业智能评级系统的端到端流水线：企业清单 → 集成爬取4维度信息 →
技术画像补强 → 规则引擎评分 → DeepSeek 深度评级 → **模型评价与验证** →
报告/individual.csv → 多机数据同步。**每次运行必须写日志到 logs/，运行后
复盘，并把新发现的效率优化点更新回本 skill**（本 skill 是可持续进化的
运行手册）。

项目根目录: `/Users/kc/Desktop/E-InfoInsight-agent-codes`
数据库: PostgreSQL rating_system (DATABASE_URL 环境变量)
Python: `.venv/bin/activate` 后执行

## When to Use

- 触发: 全量重扫、每日增量更新、热点追踪、新企业批量接入、
  多机数据同步、采集效率变差需要排查
- 不用: 只调单个模块（评分/评级/报告）时用对应 skill
  (rating-crawl / rating-score / rating-analyze / rating-report)

## 脚本调用顺序（速查表）

| 场景 | 脚本 | 调用顺序 |
|------|------|---------|
| 全量重采 | scripts/integrated_crawl.py | 清空关联表→新闻→技术→招聘→招投标→规则评分(full)→导出线索 |
| 技术补强 | scripts/supplement_tech.py | KNOWN_TECH 更新 tech_profiles→全量重评分 |
| DeepSeek评级 | scripts/run_deepseek_rating.py [--mode full\|incremental] | 达标企业→分批评级→写库 |
| 独立输出 | scripts/export_individual.py | individual.csv (15列, 规则+LLM双评级) |
| **结果验证** | **scripts/verify_results.py [--limit N]** | **规则校验→模型判定(评分合理性+数据真实性)→verification_<ts>.md** |
| 每日增量 | scripts/daily_update.sh | business增量→recruitment→news→评分→评级→日报 |
| 全量脚本 | scripts/full_scan.sh | business→tech→recruitment→news→bidding→评分→评级→报告 |
| 热点追踪 | scripts/hot_track.sh | news(S,A)→重评(hot_track)→追踪报告 |
| 多机同步 | scripts/export_sync.py / scripts/import_sync.py | 爬取机导出→git push / 汇聚机 pull→导入 |

## 推荐全链路流程（实战验证版）

### Step 1 — 环境检查
```bash
cd /Users/kc/Desktop/E-InfoInsight-agent-codes && source .venv/bin/activate
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('KEY:', 'OK' if os.getenv('DEEPSEEK_API_KEY') else 'MISSING')"
psql -d rating_system -c "SELECT status, count(*) FROM companies GROUP BY status"
```
完成标准: API Key 存在、DB 可连、明确当前企业状态分布（raw/scored/rated/filtered）。

### Step 2 — 企业清单
- 来源: `companies` 表（seed_real.sql 真实企业，含 credit_code）
- 全量: `SELECT id, company_name, credit_code FROM companies ORDER BY id`
- 增量: 只看 status='raw' 或 updated_at 超期企业
完成标准: 清单数量与目标一致，信用代码无空值。

### Step 3 — 集成爬取（优先于 6 个独立 spider）
```bash
python scripts/integrated_crawl.py > logs/run_$(date +%Y%m%d_%H%M%S).log 2>&1
```
- 后台运行 + notify_on_complete，期间勿并行跑其他爬虫（会清空关联表）
- 内部顺序: 清空 news/tech/recruit/bidding → 新闻(百度/搜狗/必应聚合) →
  技术画像(GitHub+搜索) → 招聘(搜索推断) → 招投标(搜索推断)
- 耗时参考: 15家企业约5-8分钟（GitHub 失败时每家多30-40秒）
完成标准: 日志含"爬取完成!"与"评分完成: 总计N家, 通过M家"。

### Step 4 — 技术画像补强（GitHub 不可达时必需）
```bash
python scripts/supplement_tech.py
```
- 用 KNOWN_TECH（真实公开信息: 云厂商/GitHub组织/技术栈）覆盖更新
  tech_profiles，随后全量重评分
- **为何必需**: api.github.com 在多数国内网络 SSL 被切断，集成爬取的
  github 字段会全空，直接影响 tech_investment 维度得分
完成标准: "共更新 N/N 家"且重评分后通过企业数 ≥ 补强前。

### Step 5 — 规则引擎评分
- integrated_crawl.py 已内含（mode=full）；单独跑:
  `python engine/rules_engine.py --mode full`
- 阈值: pass_threshold=40（B级达标，达标企业才送 DeepSeek，省 token）
完成标准: `SELECT status,count(*) FROM companies GROUP BY status`
  全部 scored；ratings 有 rules_engine 记录。

### Step 6 — DeepSeek 评级
```bash
python scripts/run_deepseek_rating.py --mode full
```
- 只评达标企业（status='scored' 且 ≥40分），分批3家/批
- 断点续跑: data/.llm_progress.json，失败批次重跑自动跳过已完成
完成标准: `SELECT rating_level,count(*) FROM ratings WHERE rated_by='deepseek'
  GROUP BY rating_level` 有分布；达标企业全部 status='rated'。

### Step 7 — 报告与独立输出
```bash
python scripts/export_individual.py   # individual.csv（最终交付物）
python engine/report.py --date $(date +%Y-%m-%d)   # 日报/线索(可选)
```
完成标准: data/reports/individual.csv 存在且 15 列对齐，llm 列有值。

### Step 8 — 模型评价与验证（评分合理性 + 数据真实性）
```bash
python scripts/verify_results.py            # 全部企业
python scripts/verify_results.py --limit 5  # 快速抽查
```
- 规则校验（零模型）: 信用代码18位/91前缀、名称与经营范围非空
- 模型判定（DeepSeek 分批3家）: 每家输出 score_check(合理/偏高/偏低) +
  data_check(可信/存疑/可疑) + 依据 + 风险点
- 输出: data/reports/verification_<ts>.md（分布统计 + 明细表 + 需关注企业）
- **判定解读**: 数据"存疑/可疑"→ 回查爬取源; 评分"偏高/偏低"集中 →
  校准 scoring_rules.yaml; 两模型等级差异大(如A vs C) → 核查评级标准
完成标准: 判定完成率 100%（15/15），报告含分布统计；问题企业已记录。

### Step 9 — 多机同步（如有第二台机器）
```bash
# 爬取机: python scripts/export_sync.py && git add data/sync && git commit -m "sync: data" && git push
# 汇聚机: git pull && python scripts/import_sync.py
```
完成标准: 导入统计行数 = 导出行数，二次导入幂等（行数不变）。

### Step 10 — 日志汇总与复盘
- 写 logs/run_<ts>_summary.md：各阶段耗时/采集量/失败点/修复记录
- **复盘优化**: 对比上次运行（采集量、耗时、失败项），新发现立即以
  patch 方式更新到本 skill 的"效率优化参考"章节，保持手册新鲜

## 效率优化参考（实战经验，持续更新）

1. **integrated_crawl.py 优先**: 6 个独立 scrapy spider 框架开销大、
   且 business_spider 依赖 gsxt 严格反爬；集成脚本直接 requests 聚合
   搜索，零模型依赖、15家5-8分钟可完成
2. **GitHub API 不可达是常态**: 直接跑 supplement_tech.py 用 KNOWN_TECH
   补强（真实公开信息，比 API 快且稳定），不要等 API 重试
3. **DeepSeek JSON 截断**: max_tokens 默认已改 8000、batch_size=3；
   若再遇"JSON解析失败"→ 再降 batch_size（每批更少企业，输出更短）
4. **断点续跑**: llm_client 进度文件 data/.llm_progress.json；
   注意其清除逻辑按数量判断，跨批次遗留会误清（下次全重跑时留意）
5. **数据库幂等**: 4张关联表已有唯一约束 + ON CONFLICT DO NOTHING，
   重跑/多机并发不会重复插入；companies 按 credit_code upsert
6. **网络诊断**: 境外主机（github/ezone.ksyun）超时而国内正常 =
   代理或出口问题，先 curl 三连测（baidu/github/ezone）再决定重试
7. **日志先行**: 所有长任务 tee 到 logs/run_<ts>.log，后台跑 +
   notify_on_complete，避免阻塞
8. **deepseek-v4-flash 是推理模型**: reasoning_content 会吃 max_tokens
   预算，预算不足时 content 返回空(finish=length)——所有调用必须
   max_tokens≥8000 且对"200但content空"做重试；批量输出建议 batch≤3
9. **验证脚本网络波动容错**: verify_results 批次4曾遇 ChunkedEncodingError
   （响应提前中断），自动重试后成功；长文本响应时网络波动概率上升，
   遇异常先重试不要改参数

## Common Pitfalls

1. **并行跑爬虫**: integrated_crawl.py 开头会清空关联表，与独立 spider
   并行会互相覆盖数据。串行执行。
2. **GitHub 字段全空**: 看到 github=None 刷屏不要等重试，直接
   supplement_tech.py 补强。
3. **DeepSeek 批次失败不重试**: 失败批次会被跳过（非致命），重跑
   run_deepseek_rating.py 即补；不要手动重复调用 API。
4. **individual.csv 列错位**: 该脚本 SQL 曾多选 id 列导致错位，已修复；
   改动后验证表头前8列与 COLUMNS 一致。
5. **push 超时**: ezone.ksyun.com 偶发不可达，本地 commit 安全，网络
   恢复后 git push origin test 即可；勿反复强制操作。
6. **多机同时爬同一批企业**: 浪费且触发反爬；各机分配不同 spider/
   关键词，或等汇聚机导入后再爬。
7. **验证脚本 max_tokens 不足**: 若模型判定率 <100%，检查是否为
   finish=length（reasoning 吃满预算），max_tokens 提到 8000+。

## Verification Checklist

- [ ] 环境检查通过（API Key / DB / 状态分布）
- [ ] 采集完成且日志落盘（news>0, tech=全部企业, recruit>0）
- [ ] 技术画像补强 15/15（或 N/N）
- [ ] 规则评分: 全部 scored，达标企业 ≥40 分
- [ ] DeepSeek: 达标企业全部 rated，level∈S/A/B/C/D
- [ ] individual.csv 存在、15列对齐、含 llm 评级
- [ ] 验证报告生成且判定完成率 100%，数据"存疑/可疑"为 0
- [ ] 评分"偏高/偏低"企业已记录并评估校准需求
- [ ] logs/run_<ts>_summary.md 已写，复盘结论已回写本 skill
- [ ] （多机）data/sync 已 push / 已 pull 导入且幂等
