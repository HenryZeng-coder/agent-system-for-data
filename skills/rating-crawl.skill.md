---
name: rating-crawl
description: 启动武汉IT企业爬虫采集流程
---

# 爬虫编排

## 流程
1. 检查爬虫进程是否在运行
2. 清空 data/raw/ 临时目录
3. 启动 Scrapy 爬虫 (terminal background)
4. 每30秒轮询爬虫状态
5. 数据验证
6. 输出摘要 (采集数/去重数/过滤数/入库数)

## 配置
- 项目目录: ~/Desktop/E-infoinsight-agent-codes/crawler
- 超时: 72h(全量) / 4h(增量)

## 验证
- 数据行数 > 0
- company_name 非空率 > 95%
- credit_code 非空率 > 90%
