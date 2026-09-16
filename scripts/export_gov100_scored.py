#!/usr/bin/env python3
"""导出政府名单前100家评分结果到 CSV (data/potential_companies/0_government_certified_100_scored.csv)"""
import os, sys, csv, psycopg2
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

db_url = os.getenv("DATABASE_URL")
conn = psycopg2.connect(db_url)
with conn.cursor() as cur:
    cur.execute(
        """SELECT c.id, c.company_name, c.industry_tags,
                  left(c.business_scope, 80) AS business_scope,
                  c.registered_capital, c.capital_amount, c.established_date,
                  r.total_score, r.rating_level,
                  r.tech_score, r.funding_score, r.intent_score, r.team_score, r.industry_score,
                  tp.tech_stack, tp.cloud_provider, tp.has_github_org, tp.has_tech_blog, tp.ai_job_ratio,
                  (SELECT COUNT(*) FROM recruitments WHERE company_id = c.id) AS hire_count,
                  (SELECT COUNT(*) FROM news_mentions WHERE company_id = c.id) AS news_count,
                  (SELECT COUNT(*) FROM bidding_records WHERE company_id = c.id AND is_digital = TRUE) AS dig_bid_count
           FROM companies c
           LEFT JOIN ratings r ON r.company_id = c.id AND r.rated_by = 'rules_engine'
           LEFT JOIN tech_profiles tp ON tp.company_id = c.id
           WHERE c.id >= 136
           ORDER BY r.total_score DESC NULLS LAST"""
    )
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
conn.close()

out = os.path.join(PROJECT_ROOT, "data", "potential_companies", "0_government_certified_100_scored.csv")
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(columns)
    for row in rows:
        w.writerow([("" if v is None else v) for v in row])
print(f"导出 {len(rows)} 家 -> {out}")
