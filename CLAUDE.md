# 武汉IT企业智能评级系统

## 项目结构
- `config/` — 配置文件 (config.yaml, scoring_rules.yaml)
- `db/` — 数据库DDL和种子数据
- `crawler/` — Scrapy爬虫 (6个Spider + 5级管道)
- `engine/` — 规则引擎 + DeepSeek客户端 + 报告生成
- `skills/` — Hermes Agent Skills (4个)
- `scripts/` — 运维脚本
- `tests/` — 单元测试

## 开发流程
详见 `docs/开发流程.md` — 按步骤逐步执行的完整开发指南。

## 关键文档
- `docs/开发流程.md` — 分步开发指南 (可作为 prompt 逐步执行)
- `docs/代码准备及层级结构文档.md` — 完整架构设计 (在 rating_system 项目中)

## 环境要求
- Python 3.11+
- PostgreSQL 16
- Scrapy 2.11+
- 详见 requirements.txt

## 快速开始
```bash
bash scripts/setup.sh
```
