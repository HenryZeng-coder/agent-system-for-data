#!/usr/bin/env python3
"""补全 all_rated_companies 前3家公司 (长飞光纤/奇安信武汉/融芯智能) 的真实工商数据

数据来源:
- 长飞光纤: 东方财富 F10 (SH601869) — 上市公司年报披露
- 奇安信(武汉): 百度百科词条 — 奇安信安全技术（武汉）有限公司
- 融芯智能: 水滴信用 shuidi.cn — 国家企业信用信息公示系统数据

修正内容:
- registered_address (原为空)
- legal_representative (原为空/错误)
- established_date (原为空/错误)
- capital_amount / registered_capital (原与实际不符)
- 奇安信公司名修正: 武汉奇安信科技有限公司 -> 奇安信安全技术（武汉）有限公司
"""
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# 真实工商数据 (来源标注)
UPDATES = [
    {
        "db_name": "武汉长飞光纤光缆股份有限公司",
        "company_name": "长飞光纤光缆股份有限公司",   # 真实注册名
        "credit_code": "91420100616400352X",         # 东财F10 REG_NUM
        "registered_capital": "82790.5108万元",
        "capital_amount": 82790.51,
        "established_date": "1988-05-31",
        "legal_representative": "马杰",
        "registered_address": "湖北省武汉市东湖高新技术开发区光谷大道9号",
        "source": "东方财富F10 (SH601869)",
    },
    {
        "db_name": "武汉奇安信科技有限公司",
        "company_name": "奇安信安全技术（武汉）有限公司",  # 真实注册名
        "credit_code": "91420100MA4KXNYJ1C",
        "registered_capital": "1000万元",
        "capital_amount": 1000.00,
        "established_date": "2019-12-20",
        "legal_representative": "吴云坤",
        "registered_address": "武汉临空港经济技术开发区",
        "source": "百度百科",
    },
    {
        "db_name": "武汉融芯智能科技有限公司",
        "company_name": "武汉融芯智能科技有限公司",
        "credit_code": "91420100MABTNX8857",
        "registered_capital": "300万人民币",
        "capital_amount": 300.00,
        "established_date": "2022-07-14",
        "legal_representative": "刘晓龙",
        "registered_address": "湖北省武汉市东湖新技术开发区光谷大道110号当代国际花园总部基地5号楼302室",
        "source": "水滴信用(国家企业信用信息公示系统)",
    },
]


def main():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    try:
        for u in UPDATES:
            with conn.cursor() as cur:
                cur.execute("SELECT id, company_name, registered_address FROM companies WHERE company_name = %s", (u["db_name"],))
                row = cur.fetchone()
                if not row:
                    logger.warning(f"未找到企业: {u['db_name']}")
                    continue
                cid = row[0]
                cur.execute(
                    """UPDATE companies SET
                        company_name = %s,
                        credit_code = %s,
                        registered_capital = %s,
                        capital_amount = %s,
                        established_date = %s,
                        legal_representative = %s,
                        registered_address = %s,
                        updated_at = NOW()
                       WHERE id = %s""",
                    (u["company_name"], u["credit_code"], u["registered_capital"],
                     u["capital_amount"], u["established_date"], u["legal_representative"],
                     u["registered_address"], cid),
                )
                logger.info(f"✓ 更新 {u['db_name']} → {u['company_name']} (id={cid}, 来源: {u['source']})")
        conn.commit()
        logger.info("3 家企业工商数据补全完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
