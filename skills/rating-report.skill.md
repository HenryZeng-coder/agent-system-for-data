---
name: rating-report
description: 生成评级报告并导出销售线索
---

# 报告与线索导出

## 流程
1. 读取 status='rated' 的企业数据
2. 生成评级分布报告 (S/A/B/C/D 数量)
3. 导出 S/A 级企业为 CSV/Excel
4. 如有新 S/A 级企业，发送通知
5. 更新 status='filtered'

## 输出
- data/reports/daily_{date}.md
- data/reports/leads_{date}.csv
- data/reports/leads_{date}.xlsx
