#!/usr/bin/env python3
"""DeepSeek 批量评级驱动 — 对规则引擎达标企业执行深度评级

用法: python scripts/run_deepseek_rating.py [--mode full|incremental]
流程: get_companies_for_llm(达标) → batch_rate(分批调用+断点续跑) → update_database
"""
import os
import sys
import logging

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("full", "incremental") else "full"
    db_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not db_url or not api_key or api_key.startswith("your"):
        logger.error("缺少 DATABASE_URL 或 DEEPSEEK_API_KEY")
        sys.exit(1)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from engine.rules_engine import RatingRulesEngine
    from engine.llm_client import LLMRatingClient

    engine = RatingRulesEngine()
    companies = engine.get_companies_for_llm(db_url)
    logger.info(f"达标企业 (>= {engine.pass_threshold}分): {len(companies)} 家")
    for c in companies:
        logger.info(f"  {c.get('company_name', '未知')}: {c.get('total_score', 0)}分")

    client = LLMRatingClient(api_key=api_key, max_tokens=8000, batch_size=3)
    results = client.batch_rate(companies, mode=mode)

    if results:
        client.update_database(results, db_url)
        logger.info(f"DeepSeek评级完成: {len(results)} 家")
    else:
        logger.warning("DeepSeek评级无结果 (检查API Key和网络)")

    # 分布统计
    from collections import Counter
    levels = Counter(r.get("level") for r in results)
    logger.info(f"DeepSeek评级分布: {dict(levels)}")


if __name__ == "__main__":
    main()
