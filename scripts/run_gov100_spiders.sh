#!/usr/bin/env bash
# 政府名单前100家: 依次运行 spiders 爬取4维数据
set -e
cd "$(dirname "$0")/../crawler"
source ../.venv/bin/activate
export PYTHONUNBUFFERED=1
LOG=../logs/gov100_crawl_$(date +%Y%m%d_%H%M%S).log

echo "=== 开始时间: $(date) ===" | tee -a "$LOG"

for SPIDER in websearch news tech recruitment bidding; do
  echo "" | tee -a "$LOG"
  echo "=== [$SPIDER] 开始: $(date) ===" | tee -a "$LOG"
  python -m scrapy crawl "$SPIDER" -L INFO >> "$LOG" 2>&1 || echo "[$SPIDER] FAILED (exit=$?)" | tee -a "$LOG"
  echo "=== [$SPIDER] 结束: $(date) ===" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "=== 全部完成: $(date) ===" | tee -a "$LOG"
