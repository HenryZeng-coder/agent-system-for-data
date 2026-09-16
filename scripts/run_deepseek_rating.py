#!/usr/bin/env python3
"""DeepSeek 批量评级驱动 — 对规则引擎达标企业执行深度评级

用法:
    python scripts/run_deepseek_rating.py [full|incremental|hot_track] [--levels S,A] [--limit N]

流程: 选企(规则达标企业 / --levels 指定等级) → batch_rate(分批调用+断点续跑) → update_database

说明: 实际流程实现在 engine.llm_client.run_batch_rating,
      与 `python engine/llm_client.py --mode <x>` 共用同一份代码。
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    parser = argparse.ArgumentParser(description="DeepSeek 批量评级")
    parser.add_argument(
        "mode", nargs="?", default="full",
        choices=["full", "incremental", "hot_track"],
        help="评级模式, 同时作为断点续跑进度文件的 key (默认: full)",
    )
    parser.add_argument(
        "--levels", default="",
        help="仅重评指定等级的企业, 如 S,A (热点追踪用); 留空则取规则引擎达标企业",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="只处理前 N 家 (0=全部, 小样本验证用)",
    )
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not db_url or not api_key or api_key.startswith("your"):
        logger.error("缺少 DATABASE_URL 或 DEEPSEEK_API_KEY")
        sys.exit(1)

    from engine.llm_client import run_batch_rating

    run_batch_rating(db_url, api_key, mode=args.mode, levels=args.levels, limit=args.limit)


if __name__ == "__main__":
    main()
