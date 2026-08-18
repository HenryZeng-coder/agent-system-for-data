#!/usr/bin/env python3
"""
将 data/potential_companies/1_software_it_services.csv 的 100 家公司
导入 companies 表 (status='raw'), 供爬虫补全数据后评分。

- credit_code 留空 (CSV 无此字段, 后续可由 business_spider 补全)
- capital_amount 由 registered_capital 文本解析 (万元数值)
- industry_tags 转 TEXT[] 数组
- 已存在的同名企业 (company_name) 跳过, 不重复插入
"""

import csv
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import psycopg2  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "1_software_it_services.csv")


def parse_capital_amount(text: str) -> float:
    """registered_capital 文本 → 万元数值 (与 standardize_pipeline 一致口径)"""
    if not text:
        return 0.0
    t = text.strip()
    m = re.search(r"([\d.]+)\s*亿美元", t)
    if m:
        return float(m.group(1)) * 10000 * 7.2
    m = re.search(r"([\d.]+)\s*万?美元", t)
    if m:
        return float(m.group(1)) * 7.2  # 万美元 → 万元
    m = re.search(r"([\d.]+)\s*亿", t)
    if m:
        return float(m.group(1)) * 10000
    m = re.search(r"([\d.]+)\s*万", t)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", t)
    if m:
        return float(m.group(1))
    return 0.0


def parse_year(text: str):
    """established_year → ISO 日期 (取该年1月1日)"""
    try:
        y = int(str(text).strip())
        if 1900 <= y <= 2026:
            return f"{y}-01-01"
    except (ValueError, TypeError):
        pass
    return None


def main():
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    db_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(db_url)

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"读取 CSV: {len(rows)} 家公司")

    inserted, skipped = 0, 0
    with conn.cursor() as cur:
        # 预加载已存在公司名 (DB 已有的不重复插)
        cur.execute("SELECT company_name FROM companies")
        existing = {r[0] for r in cur.fetchall()}

        for row in rows:
            name = (row.get("company_name") or "").strip()
            if not name or name in existing:
                skipped += 1
                continue
            scope = (row.get("business_scope") or "").strip()
            cap_text = (row.get("registered_capital") or "").strip()
            tags = [t.strip() for t in (row.get("industry_tags") or "").split(",") if t.strip()]
            est = parse_year(row.get("established_year"))
            cap_amount = parse_capital_amount(cap_text)

            cur.execute(
                """
                INSERT INTO companies
                    (company_name, registered_capital, capital_amount,
                     established_date, business_scope, industry_tags, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'raw')
                RETURNING id
                """,
                (name, cap_text, cap_amount, est, scope, tags if tags else None),
            )
            new_id = cur.fetchone()[0]
            existing.add(name)
            inserted += 1
    conn.commit()
    conn.close()
    print(f"✅ 导入完成: 新增 {inserted} 家, 跳过(已存在) {skipped} 家 (status='raw')")


if __name__ == "__main__":
    main()
