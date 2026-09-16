#!/bin/bash
# 每日增量更新
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true

echo "📅 每日增量更新开始 $(date)"

# 1. 增量爬虫
echo "🕷️ 增量爬虫..."
cd crawler && scrapy crawl business -s JOBDIR=jobs/incremental && scrapy crawl recruitment && scrapy crawl news && cd ..

# 2. 增量评分
echo "⚙️ 规则引擎评分..."
python engine/rules_engine.py --mode incremental

# 3. 增量DeepSeek评级
echo "🤖 DeepSeek评级..."
python engine/llm_client.py --mode incremental

# 4. 日报
echo "📊 生成日报..."
python engine/report.py --date $(date +%Y-%m-%d)

echo "✅ 增量更新完成 $(date)"
