#!/bin/bash
# 热点追踪 — 每6小时检查S/A级企业最新动态
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true

echo "🔥 热点追踪开始 $(date)"

# 1. 搜索S/A级企业最新动态
echo "🔍 搜索最新动态..."
cd crawler && scrapy crawl news -a levels=S,A && cd ..

# 2. 重新评级有变化的企业
echo "🤖 重新评级..."
python engine/llm_client.py --mode hot_track

# 3. 生成追踪报告
echo "📊 追踪报告..."
python engine/report.py --date $(date +%Y-%m-%d) --levels S,A

echo "✅ 热点追踪完成 $(date)"
