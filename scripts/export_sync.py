#!/usr/bin/env python3
"""导出全部数据表为 CSV (方案D: git+文件同步, 爬取机执行)

用法: python scripts/export_sync.py
输出: data/sync/<table>.csv (utf-8-sig, 含表头)
表:   companies, tech_profiles, recruitments, news_mentions,
      bidding_records, ratings   (crawl_tasks 为本地任务状态, 不同步)
数组字段 (industry_tags/tech_stack/tech_keywords/demand_tags) 以 JSON 序列化。
"""
import os
import csv
import json
import sys
import logging

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

TABLES = ["companies", "tech_profiles", "recruitments",
          "news_mentions", "bidding_records", "ratings"]
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sync")


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("缺少 DATABASE_URL")
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    os.makedirs(OUT_DIR, exist_ok=True)

    for table in TABLES:
        cur.execute(f"SELECT * FROM {table} ORDER BY id")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        path = os.path.join(OUT_DIR, f"{table}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            for row in rows:
                writer.writerow([
                    json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else
                    ("" if v is None else v)
                    for v in row
                ])
        logger.info(f"导出 {table}: {len(rows)} 行 → {os.path.abspath(path)}")

    cur.close()
    conn.close()
    logger.info("导出完成")


if __name__ == "__main__":
    main()
