#!/usr/bin/env python3
"""
将 data/potential_companies/0_government_certified_500.csv 的前100家公司
导入 companies 表 (status='raw'), 供爬虫补全数据后评分。

政府名单 CSV 只有 company_name + source_category, 无工商字段:
- business_scope 留空 (后续由爬虫/补全脚本填充)
- industry_tags 用 source_category 作为近似标签
- credit_code 留空
"""
import csv
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import psycopg2  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "0_government_certified_500.csv")
LIMIT = 100  # 只取前100家


def main():
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    db_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(db_url)

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))[:LIMIT]
    print(f"读取 CSV 前 {len(rows)} 家公司")

    inserted, skipped = 0, 0
    with conn.cursor() as cur:
        cur.execute("SELECT company_name FROM companies")
        existing = {r[0] for r in cur.fetchall()}

        for row in rows:
            name = (row.get("company_name") or "").strip()
            if not name or name in existing:
                skipped += 1
                continue
            category = (row.get("source_category") or "").strip()
            tags = [category] if category else None
            cur.execute(
                """
                INSERT INTO companies
                    (company_name, business_scope, industry_tags, status)
                VALUES (%s, %s, %s, 'raw')
                RETURNING id
                """,
                (name, "", tags),
            )
            new_id = cur.fetchone()[0]
            existing.add(name)
            inserted += 1
            print(f"  [{new_id}] {name} ({category})")
    conn.commit()
    conn.close()
    print(f"✅ 导入完成: 新增 {inserted} 家, 跳过(已存在) {skipped} 家 (status='raw')")


if __name__ == "__main__":
    main()
