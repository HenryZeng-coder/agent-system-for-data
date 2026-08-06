#!/usr/bin/env python3
"""导出 individual.csv — 每家企业的最终评级结果独立文件

输出: data/reports/individual.csv (utf-8-sig, Excel兼容)
字段: 企业名称, 信用代码, 行业标签, 经营范围, 规则总分, 规则等级,
      DeepSeek总分, DeepSeek等级, 需求标签, 销售话术, 评级理由,
      新闻条数, 招聘条数, 招投标数, 评级时间
"""
import os
import csv
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "reports", "individual.csv")

COLUMNS = [
    "company_name", "credit_code", "industry_tags", "business_scope",
    "rules_score", "rules_level",
    "llm_score", "llm_level", "demand_tags", "sales_pitch", "reasoning",
    "news_count", "recruitment_count", "bidding_count", "rated_at",
]


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("缺少 DATABASE_URL")
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.company_name, c.credit_code, c.industry_tags, c.business_scope,
               rr.total_score AS rules_score, rr.rating_level AS rules_level,
               lr.total_score AS llm_score, lr.rating_level AS llm_level,
               lr.demand_tags, lr.sales_pitch, lr.reasoning,
               (SELECT count(*) FROM news_mentions n WHERE n.company_id = c.id) AS news_count,
               (SELECT count(*) FROM recruitments r WHERE r.company_id = c.id) AS recruitment_count,
               (SELECT count(*) FROM bidding_records b WHERE b.company_id = c.id) AS bidding_count,
               COALESCE(lr.rated_at, rr.rated_at) AS rated_at
        FROM companies c
        LEFT JOIN ratings rr ON rr.company_id = c.id AND rr.rated_by = 'rules_engine'
        LEFT JOIN ratings lr ON lr.company_id = c.id AND lr.rated_by = 'deepseek'
        ORDER BY COALESCE(lr.total_score, rr.total_score, 0) DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow(row)

    logger.info(f"已导出 {len(rows)} 家企业到 {os.path.abspath(OUTPUT_PATH)}")

    # 控制台摘要
    print(f"\n{'公司名称':<22} {'信用代码':<20} {'规则':>5} {'LLM':>5}")
    print("-" * 60)
    for r in rows:
        name = r[0] or ""
        code = r[1] or ""
        rs = f"{r[4]}{r[5]}" if r[4] is not None else "-"
        ls = f"{r[6]}{r[7]}" if r[6] is not None else "-"
        print(f"{name:<22} {code:<20} {rs:>5} {ls:>5}")
    print(f"\n总计: {len(rows)} 家")


if __name__ == "__main__":
    main()
