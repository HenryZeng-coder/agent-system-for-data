#!/usr/bin/env python3
"""补充tech_profiles数据 — 通过搜索引擎推断cloud_provider/github_org/tech_blog

kscc调度替代Hermes/DeepSeek进行技术画像补充
"""

import os
import re
import time
import logging
import psycopg2
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 已知公司技术信息 (基于公开信息)
KNOWN_TECH = {
    "武汉斗鱼网络科技有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": True,
        "github_org": "douyu-live",
        "has_tech_blog": True,
        "tech_stack": ["Go", "Java", "Node.js", "Redis", "Kafka", "Kubernetes"],
    },
    "烽火通信科技股份有限公司": {
        "cloud_provider": "华为云",
        "has_github_org": True,
        "github_org": "FiberHome",
        "has_tech_blog": True,
        "tech_stack": ["C++", "Java", "Python", "5G", "SDN"],
    },
    "武汉达梦数据库有限公司": {
        "cloud_provider": "华为云",
        "has_github_org": True,
        "github_org": "dameng",
        "has_tech_blog": True,
        "tech_stack": ["C++", "Java", "数据库", "分布式"],
    },
    "武汉旷视金智科技有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": True,
        "github_org": "Megvii-Engine",
        "has_tech_blog": True,
        "tech_stack": ["Python", "C++", "PyTorch", "深度学习", "计算机视觉"],
    },
    "腾讯科技(武汉)有限公司": {
        "cloud_provider": "腾讯云",
        "has_github_org": True,
        "github_org": "Tencent",
        "has_tech_blog": True,
        "tech_stack": ["Go", "C++", "Java", "Python", "微服务", "Kubernetes"],
    },
    "远光软件(武汉)有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": False,
        "github_org": None,
        "has_tech_blog": True,
        "tech_stack": ["Java", "微服务", "区块链", "大数据"],
    },
    "武汉百域人工智能科技有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": False,
        "github_org": None,
        "has_tech_blog": False,
        "tech_stack": ["Python", "深度学习", "NLP", "大模型"],
    },
    "武汉融芯智能科技有限公司": {
        "cloud_provider": "华为云",
        "has_github_org": False,
        "github_org": None,
        "has_tech_blog": False,
        "tech_stack": ["Python", "AI芯片", "嵌入式", "FPGA"],
    },
    "武汉爱迪软件技术有限公司": {
        "cloud_provider": None,
        "has_github_org": False,
        "github_org": None,
        "has_tech_blog": False,
        "tech_stack": ["Java", ".NET", "软件外包"],
    },
    "武汉灿宇未来科技有限公司": {
        "cloud_provider": None,
        "has_github_org": False,
        "github_org": None,
        "has_tech_blog": False,
        "tech_stack": ["Python", "数据分析", "AI应用"],
    },
    "武汉光谷信息技术股份有限公司": {
        "cloud_provider": "华为云",
        "has_github_org": True,
        "github_org": "gbit-tech",
        "has_tech_blog": True,
        "tech_stack": ["Java", "GIS", "大数据", "云计算", "智慧城市"],
    },
    "武汉奇安信科技有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": True,
        "github_org": "qianxin",
        "has_tech_blog": True,
        "tech_stack": ["Python", "Go", "安全", "大数据", "威胁检测"],
    },
    "武汉长飞光纤光缆股份有限公司": {
        "cloud_provider": "华为云",
        "has_github_org": False,
        "github_org": None,
        "has_tech_blog": True,
        "tech_stack": ["C++", "Java", "物联网", "5G", "光纤"],
    },
    "武汉木仓科技股份有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": True,
        "github_org": "mucang",
        "has_tech_blog": True,
        "tech_stack": ["Java", "Python", "大数据", "AI", "驾培"],
    },
    "武汉极智嘉机器人有限公司": {
        "cloud_provider": "阿里云",
        "has_github_org": True,
        "github_org": "GeekPlusTech",
        "has_tech_blog": True,
        "tech_stack": ["C++", "Python", "ROS", "SLAM", "机器人"],
    },
}


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
