#!/bin/bash
# 全量重跑
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
echo "🔄 全量重跑开始 $(date)"
echo "🕷️ 阶段1: 全量爬虫..."
cd crawler && scrapy crawl business && scrapy crawl tech && scrapy crawl recruitment && scrapy crawl news && scrapy crawl bidding && cd ..
echo "⚙️ 阶段2: 规则引擎评分..."
python engine/rules_engine.py --mode full
echo "🤖 阶段3: DeepSeek评级..."
python engine/llm_client.py --mode full
echo "📊 阶段4: 生成报告..."
python engine/report.py --date $(date +%Y-%m-%d)
echo "✅ 全量重跑完成 $(date)"
