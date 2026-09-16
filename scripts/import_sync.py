#!/usr/bin/env python3
"""从 data/sync/*.csv 幂等导入 (方案D: git+文件同步, 汇聚机执行)

用法: python scripts/import_sync.py [--update-ratings]
策略:
- companies:      按 credit_code upsert (约束 uq/credit_code UNIQUE), 建立 id 映射
- tech_profiles:  company_id 重映射 + ON CONFLICT (company_id) DO NOTHING
- recruitments:   company_id 重映射 + ON CONFLICT (company_id, position_title, source_name) DO NOTHING
- news_mentions:  company_id 重映射 + ON CONFLICT (company_id, title, source_name) DO NOTHING
- bidding_records:company_id 重映射 + ON CONFLICT (company_id, project_name, source_name) DO NOTHING
- ratings:        company_id 重映射 + ON CONFLICT (company_id, rated_by) DO UPDATE
                  (默认 DO NOTHING 保留本地; --update-ratings 时以导入文件覆盖)
前置: 目标库需已存在唯一约束 (init.sql 已含, 或手工 ALTER)。
"""
import os
import csv
import json
import sys
import logging
from collections import Counter

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

SYNC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sync")

# 各表: (文件, 业务键列, 冲突处理)
TABLES = {
    "tech_profiles":    {"key": "company_id", "conflict": "(company_id)"},
    "recruitments":     {"key": "company_id", "conflict": "(company_id, position_title, source_name)"},
    "news_mentions":    {"key": "company_id", "conflict": "(company_id, title, source_name)"},
    "bidding_records":  {"key": "company_id", "conflict": "(company_id, project_name, source_name)"},
}


def _load_csv(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [dict(zip(header, row)) for row in reader]
    return header, rows


def _clean(v, is_array_field=False):
    """CSV 字符串 → Python 值 (空串→None, JSON数组→list)"""
    if is_array_field:
        if v is None or v == "":
            return None
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    if v is None or v == "":
        return None
    return v


def main():
    update_ratings = "--update-ratings" in sys.argv
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("缺少 DATABASE_URL")
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()
    stats = Counter()

    try:
        # ============ 1. companies: 按 credit_code upsert + id 映射 ============
        header, rows = _load_csv(os.path.join(SYNC_DIR, "companies.csv"))
        id_map = {}
        array_fields = {"industry_tags"}
        for row in rows:
            credit_code = row.get("credit_code")
            if not credit_code:
                logger.warning(f"跳过无信用代码企业: {row.get('company_name')}")
                stats["companies_skipped"] += 1
                continue
            data = {k: _clean(v, k in array_fields) for k, v in row.items() if k != "id"}
            cur.execute(
                """
                INSERT INTO companies (company_name, credit_code, registered_capital,
                    capital_amount, established_date, legal_representative,
                    business_scope, registered_address, status, industry_tags,
                    source_url, funding_stage)
                VALUES (%(company_name)s, %(credit_code)s, %(registered_capital)s,
                    %(capital_amount)s, %(established_date)s, %(legal_representative)s,
                    %(business_scope)s, %(registered_address)s, COALESCE(%(status)s,'raw'),
                    %(industry_tags)s, %(source_url)s, %(funding_stage)s)
                ON CONFLICT (credit_code) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    business_scope = EXCLUDED.business_scope,
                    registered_capital = EXCLUDED.registered_capital,
                    capital_amount = EXCLUDED.capital_amount,
                    established_date = EXCLUDED.established_date,
                    legal_representative = EXCLUDED.legal_representative,
                    registered_address = EXCLUDED.registered_address,
                    industry_tags = EXCLUDED.industry_tags,
                    source_url = EXCLUDED.source_url,
                    funding_stage = EXCLUDED.funding_stage,
                    updated_at = NOW()
                RETURNING id
                """,
                data,
            )
            new_id = cur.fetchone()[0]
            id_map[int(row["id"])] = new_id
            stats["companies"] += 1

        # ============ 2. 关联表: company_id 重映射 + ON CONFLICT DO NOTHING ============
        array_fields_map = {
            "tech_profiles": {"tech_stack"},
            "recruitments": {"tech_keywords"},
            "news_mentions": set(),
            "bidding_records": set(),
        }
        for table, cfg in TABLES.items():
            header, rows = _load_csv(os.path.join(SYNC_DIR, f"{table}.csv"))
            if not rows:
                stats[table] = 0
                continue
            cols = [c for c in header if c != "id"]
            placeholders = ", ".join(f"%({c})s" for c in cols)
            insert_sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT {cfg['conflict']} DO NOTHING"
            )
            for row in rows:
                old_cid = row.get("company_id")
                new_cid = id_map.get(int(old_cid)) if old_cid else None
                if new_cid is None:
                    stats[f"{table}_orphan"] += 1
                    continue
                data = {c: _clean(v, c in array_fields_map[table]) for c, v in row.items() if c != "id"}
                data["company_id"] = new_cid
                cur.execute(insert_sql, data)
                stats[table] += 1

        # ============ 3. ratings: company_id 重映射 ============
        header, rows = _load_csv(os.path.join(SYNC_DIR, "ratings.csv"))
        if rows:
            conflict_action = "DO UPDATE SET total_score = EXCLUDED.total_score, rating_level = EXCLUDED.rating_level, tech_score = EXCLUDED.tech_score, funding_score = EXCLUDED.funding_score, intent_score = EXCLUDED.intent_score, team_score = EXCLUDED.team_score, industry_score = EXCLUDED.industry_score, demand_tags = EXCLUDED.demand_tags, sales_pitch = EXCLUDED.sales_pitch, reasoning = EXCLUDED.reasoning, rated_at = NOW()" if update_ratings else "DO NOTHING"
            cols = ["company_id", "total_score", "rating_level", "tech_score",
                    "funding_score", "intent_score", "team_score", "industry_score",
                    "demand_tags", "sales_pitch", "reasoning", "rated_by", "rated_at"]
            insert_sql = (
                "INSERT INTO ratings (" + ", ".join(cols) + ") VALUES ("
                + ", ".join(f"%({c})s" for c in cols) + ") "
                f"ON CONFLICT (company_id, rated_by) {conflict_action}"
            )
            for row in rows:
                new_cid = id_map.get(int(row["company_id"])) if row.get("company_id") else None
                if new_cid is None:
                    stats["ratings_orphan"] += 1
                    continue
                data = {c: _clean(row.get(c), c == "demand_tags") for c in cols}
                data["company_id"] = new_cid
                cur.execute(insert_sql, data)
                stats["ratings"] += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"导入失败已回滚: {e}")
        raise
    finally:
        cur.close()
        conn.close()

    logger.info(f"导入统计: {dict(stats)}")


if __name__ == "__main__":
    main()
