---
name: rating-score
description: 对爬虫数据执行规则引擎评分
---

# 规则引擎评分

## 流程
1. 读取 status='raw' 的企业数量
2. 执行 python engine/rules_engine.py --mode {incremental|full}
3. 检查输出完整性 (scored 企业数 == raw 企业数)
4. 统计评分分布 (各分数段企业数)
5. 输出评分摘要

## 验证
- 评分分布合理 (不是全部0分或全部100分)
- score 字段范围 0-100
- status 全部更新为 'scored'
