---
name: rating-analyze
description: 调用DeepSeek对高价值企业进行深度评级
---

# DeepSeek 评级分析

## 流程
1. 读取 status='scored' 且 total_score>=50 的企业列表
2. 终端启动 python engine/llm_client.py
3. 监控 API 调用进度
4. 检查每批返回的 JSON 结构完整性
5. 写入 ratings 表
6. 标记 status='rated'
7. 输出评级摘要 (S/A/B/C/D 分布)

## 容错
- 429 限速: 自动指数退避
- 5xx 异常: 重试3次
- JSON 格式异常: 降 temperature + few-shot

## 验证
- 所有 scored(>=50) 企业都有对应 ratings 记录
- level 字段仅在 S/A/B/C/D 中
