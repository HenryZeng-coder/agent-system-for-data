#!/usr/bin/env python3
"""5号名录全量 DeepSeek 评级 + credit_code 补全

目标: 5号名录100家企业全部获得 DeepSeek 评级 (不受规则引擎40分阈值限制),
使等级分布合理 (S/A/B/C/D), 并补全企业编码 (credit_code)。

流程:
1. 从 companies 表读取 5号名录企业 (含4维采集数据)
2. 写入已获取的真实 credit_code (百度百科/东财 结果)
3. 分批 (3家/批) 调用 DeepSeek 评级 — 全部企业, 不按规则分过滤
4. 写库 ratings (rated_by='deepseek') + 更新 status='rated'
5. 导出 5_smart_manufacturing_scored.csv (18列, 含credit_code)

用法: python scripts/rate_all_category5.py [--limit N] [--no-deepseek]
"""
import os
import re
import csv
import sys
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
DATABASE_URL = os.getenv("DATABASE_URL")

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "5_smart_manufacturing.csv")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "5_smart_manufacturing_scored.csv")
BIZ_INFO = os.path.join(PROJECT_ROOT, "data", "potential_companies", "biz_info_5.csv")

OUT_COLUMNS = ["company_name", "credit_code", "registered_capital", "business_scope",
               "industry_tags", "registered_address", "funding_stage",
               "total_score", "rating_level", "tech_score", "funding_score",
               "intent_score", "team_score", "industry_score",
               "demand_tags", "sales_pitch", "reasoning", "crawl_time"]


def load_biz_info() -> dict:
    """加载已获取的工商信息 (company_name -> credit_code/address/legal)"""
    info = {}
    if os.path.exists(BIZ_INFO):
        with open(BIZ_INFO, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("credit_code"):
                    info[r["company_name"]] = r
    return info


def get_category5_companies(limit=0):
    """读取5号名录企业在DB中的完整数据"""
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        names = [(r.get("company_name") or "").strip() for r in csv.DictReader(f)]
    names = [n for n in names if n]
    if limit > 0:
        names = names[:limit]

    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    companies = []
    try:
        for name in names:
            with conn.cursor() as cur:
                cur.execute("""SELECT c.id, c.company_name, c.capital_amount, c.business_scope,
                                      c.industry_tags, c.funding_stage, c.credit_code,
                                      c.registered_capital, c.registered_address, c.legal_representative
                               FROM companies c WHERE c.company_name = %s""", (name,))
                c = cur.fetchone()
                if not c:
                    logger.warning(f"未入库: {name}")
                    continue
                cid = c[0]
                cur.execute("SELECT ai_job_ratio, cloud_provider, has_github_org, has_tech_blog "
                            "FROM tech_profiles WHERE company_id = %s", (cid,))
                t = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM recruitments WHERE company_id = %s", (cid,))
                hiring = cur.fetchone()[0]
                cur.execute("SELECT title, content_summary FROM news_mentions WHERE company_id = %s "
                            "ORDER BY published_at DESC LIMIT 5", (cid,))
                news_parts = [" ".join(p for p in (x, y) if p) for x, y in cur.fetchall()]
                cur.execute("SELECT COUNT(*) FROM bidding_records WHERE company_id = %s AND is_digital = TRUE", (cid,))
                dig_bid = cur.fetchone()[0] > 0
            companies.append({
                "company_id": cid,
                "company_name": name,
                "capital_amount": c[2] or 0,
                "business_scope": c[3] or "",
                "industry_tags": c[4] or [],
                "funding_stage": c[5] or "",
                "credit_code": c[6] or "",
                "registered_capital": c[7] or "",
                "registered_address": c[8] or "",
                "legal_rep": c[9] or "",
                "ai_job_ratio": t[0] or 0 if t else 0,
                "cloud_provider": t[1] if t else None,
                "has_github_org": bool(t[2]) if t else False,
                "has_tech_blog": bool(t[3]) if t else False,
                "hiring_count": hiring,
                "recent_news": " ".join(news_parts),
                "has_digital_bid": dig_bid,
            })
    finally:
        conn.close()
    return companies


def merge_credit_codes(companies, biz_info):
    """用已获取的真实工商信息补全 credit_code/address"""
    updated = 0
    for c in companies:
        bi = biz_info.get(c["company_name"])
        if bi:
            if not c["credit_code"] and bi.get("credit_code"):
                c["credit_code"] = bi["credit_code"]
            if not c["registered_address"] and bi.get("address"):
                c["registered_address"] = bi["address"]
            updated += 1
    logger.info(f"工商信息补全: {updated} 家 (含真实credit_code {sum(1 for c in companies if c['credit_code'])})")
    return companies


def update_db_biz_info(companies):
    """将 credit_code/address 写回 companies 表"""
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    n = 0
    try:
        for c in companies:
            if c.get("credit_code") or c.get("registered_address"):
                with conn.cursor() as cur:
                    cur.execute("UPDATE companies SET credit_code=%s, registered_address=%s, updated_at=NOW() "
                                "WHERE id=%s",
                                (c.get("credit_code") or None, c.get("registered_address") or None, c["company_id"]))
                    n += 1
        conn.commit()
        logger.info(f"已写回 companies: {n} 家")
    finally:
        conn.close()


def rate_with_deepseek(companies, limit=0):
    """对全部企业 DeepSeek 评级 (不受规则阈值限制)"""
    sys.path.insert(0, PROJECT_ROOT)
    from engine.llm_client import LLMRatingClient

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key.startswith("your"):
        logger.error("缺少 DEEPSEEK_API_KEY")
        return []

    # 过滤掉已 rated 且已有 deepseek 记录的企业
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT company_id FROM ratings WHERE rated_by='deepseek'")
            done = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    pending = [c for c in companies if c["company_id"] not in done]
    logger.info(f"DeepSeek评级: 共{len(companies)}家, 待评{len(pending)}家 (已完成{len(done)})")
    if not pending:
        return []

    client = LLMRatingClient(api_key=api_key, max_tokens=8000, batch_size=3)
    results = client.batch_rate(pending, mode="category5")
    if results:
        client.update_database(results, DATABASE_URL)
        logger.info(f"DeepSeek评级完成: {len(results)} 家")
    return results


def export_scored(companies):
    """导出18列 scored CSV"""
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    names = [c["company_name"] for c in companies]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.company_name, c.credit_code, c.registered_capital, c.business_scope, c.industry_tags,
                   c.registered_address, c.funding_stage,
                   COALESCE(lr.total_score, rr.total_score) AS total_score,
                   COALESCE(lr.rating_level, rr.rating_level) AS rating_level,
                   rr.tech_score, rr.funding_score, rr.intent_score, rr.team_score, rr.industry_score,
                   lr.demand_tags, lr.sales_pitch, lr.reasoning,
                   COALESCE(lr.rated_at, rr.rated_at) AS crawl_time
            FROM companies c
            LEFT JOIN ratings rr ON rr.company_id=c.id AND rr.rated_by='rules_engine'
            LEFT JOIN ratings lr ON lr.company_id=c.id AND lr.rated_by='deepseek'
            WHERE c.company_name = ANY(%s) ORDER BY c.id
        """, (names,))
        rows = cur.fetchall()
    conn.close()

    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(OUT_COLUMNS)
        for r in rows:
            tags = ", ".join(r[4]) if isinstance(r[4], list) else (r[4] or "—")
            demand = ", ".join(r[14]) if isinstance(r[14], list) else (r[14] or "—")
            writer.writerow([
                r[0], r[1] or "—", r[2] or "—", r[3] or "—", tags or "—",
                r[5] or "—", r[6] or "—",
                r[7] if r[7] is not None else "—",
                r[8] if r[8] else "—",
                r[9] if r[9] is not None else 0, r[10] if r[10] is not None else 0,
                r[11] if r[11] is not None else 0, r[12] if r[12] is not None else 0,
                r[13] if r[13] is not None else 0,
                demand, r[15] or "—", r[16] or "—",
                r[17].strftime("%Y-%m-%d %H:%M:%S") if r[17] else "—",
            ])
    logger.info(f"已导出 {len(rows)} 家 → {OUT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前N家(测试用)")
    parser.add_argument("--no-deepseek", action="store_true", help="跳过DeepSeek评级")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("5号名录全量评级 (所有企业送DeepSeek, 不受规则阈值限制)")
    logger.info("=" * 60)

    # 1. 读取企业 + 补全工商信息
    companies = get_category5_companies(args.limit)
    biz_info = load_biz_info()
    companies = merge_credit_codes(companies, biz_info)
    update_db_biz_info(companies)
    logger.info(f"企业总数: {len(companies)}, 含credit_code: {sum(1 for c in companies if c['credit_code'])}")

    # 2. DeepSeek 全量评级
    if not args.no_deepseek:
        rate_with_deepseek(companies, args.limit)

    # 3. 导出
    export_scored(companies)

    # 4. 等级分布统计
    from collections import Counter
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    names = [c["company_name"] for c in companies]
    with conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(lr.rating_level, rr.rating_level)
                       FROM companies c
                       LEFT JOIN ratings rr ON rr.company_id=c.id AND rr.rated_by='rules_engine'
                       LEFT JOIN ratings lr ON lr.company_id=c.id AND lr.rated_by='deepseek'
                       WHERE c.company_name = ANY(%s)""", (names,))
        levels = Counter(r[0] for r in cur.fetchall() if r[0])
    conn.close()
    logger.info(f"等级分布: {dict(levels)}")
    logger.info("全部完成")


if __name__ == "__main__":
    main()
