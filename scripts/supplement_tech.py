#!/usr/bin/env python3
"""补充 tech_profiles — 用「已知技术信息」批量回填 cloud_provider/github_org/tech_stack

已知信息放在 config/known_tech.json, 格式:
    { "企业全名": {"cloud_provider": "阿里云", "has_github_org": true,
                  "github_org": "org-name", "has_tech_blog": true,
                  "tech_stack": ["Go", "Kubernetes"]} }
文件不存在时脚本不做任何修改 (只跳过)。

用法: python scripts/supplement_tech.py
"""

import json
import os
import re
import time
import logging
import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 已知技术信息 (可编辑, 放 config/known_tech.json; 缺失则该步骤空转)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN_TECH_PATH = os.path.join(PROJECT_ROOT, "config", "known_tech.json")


def load_known_tech(path=KNOWN_TECH_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"载入已知技术信息: {len(data)} 家 ({path})")
        return data
    except FileNotFoundError:
        logger.warning(f"未找到 {path}, 本步骤无数据可补 (跳过)")
        return {}


KNOWN_TECH = load_known_tech()


def update_tech_profiles(database_url: str):
    """根据已知信息更新tech_profiles"""
    conn = psycopg2.connect(database_url)
    updated = 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tp.id, tp.company_id, c.company_name "
                "FROM tech_profiles tp JOIN companies c ON tp.company_id = c.id"
            )
            rows = cur.fetchall()

        for tp_id, company_id, name in rows:
            if name not in KNOWN_TECH:
                logger.debug(f"跳过(无已知信息): {name}")
                continue

            info = KNOWN_TECH[name]
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tech_profiles SET
                        cloud_provider = %s,
                        has_github_org = %s,
                        github_org = %s,
                        has_tech_blog = %s,
                        tech_stack = %s
                    WHERE id = %s""",
                    (
                        info.get("cloud_provider"),
                        info.get("has_github_org", False),
                        info.get("github_org"),
                        info.get("has_tech_blog", False),
                        info.get("tech_stack", []),
                        tp_id,
                    ),
                )
            updated += 1
            logger.info(f"更新tech_profile: {name} → cloud={info.get('cloud_provider')}, github={info.get('has_github_org')}, blog={info.get('has_tech_blog')}")

        conn.commit()
        logger.info(f"共更新 {updated}/{len(rows)} 家企业的tech_profiles")
    finally:
        conn.close()

    return updated


def run_full_rescore(database_url: str):
    """全量重新评分"""
    # 先将所有公司状态重置为scored (以便full模式重新评分)
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("UPDATE companies SET status = 'raw' WHERE status IN ('raw', 'scored')")
        conn.commit()
    conn.close()

    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.rules_engine import RatingRulesEngine
    engine = RatingRulesEngine()
    stats = engine.batch_score(database_url, mode="full")
    return stats


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("请设置 DATABASE_URL")
        exit(1)

    logger.info("=== 补充tech_profiles数据 ===")
    updated = update_tech_profiles(db_url)

    logger.info("\n=== 全量重新评分 ===")
    stats = run_full_rescore(db_url)
    logger.info(f"评分完成: 总计{stats['total']}家, 通过{stats['passed']}家, 未通过{stats['failed']}家")
