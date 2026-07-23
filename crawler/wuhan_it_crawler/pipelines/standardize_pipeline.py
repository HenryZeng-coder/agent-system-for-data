"""⑤ 格式标准化管道 + 数据库写入"""

import re
import logging
import psycopg2
from datetime import datetime

logger = logging.getLogger(__name__)


class StandardizePipeline:
    """格式标准化: 日期/金额统一 + 设置status='raw' + 写入数据库"""

    def __init__(self, database_url):
        self.database_url = database_url
        self.conn = None
        self.insert_count = 0
        self.update_count = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(database_url=crawler.settings.get('DATABASE_URL'))

    def open_spider(self, spider):
        self.conn = psycopg2.connect(self.database_url)
        # 批量提交: 每N条提交一次，提升写入性能
        self._batch_size = 50
        self._pending = 0

    def close_spider(self, spider):
        if self.conn:
            self.conn.commit()
            self.conn.close()
            logger.info(
                f"StandardizePipeline 关闭: 插入={self.insert_count}, "
                f"更新={self.update_count}"
            )

    def process_item(self, item, spider):
        # 金额标准化
        item['capital_amount'] = self._parse_capital(item.get('registered_capital'))

        # 日期标准化
        if item.get('established_date') and isinstance(item['established_date'], str):
            item['established_date'] = self._parse_date(item['established_date'])

        # status 设为 raw
        item['status'] = 'raw'

        # 写入数据库
        self._write_to_db(item)

        return item

    # ================================================================
    # 数据库写入
    # ================================================================

    def _write_to_db(self, item):
        """写入 companies 表，使用 ON CONFLICT 实现幂等"""
        try:
            with self.conn.cursor() as cur:
                # industry_tags 是 TEXT[] 数组，需用 psycopg2 适配
                industry_tags = item.get('industry_tags')
                if isinstance(industry_tags, str):
                    industry_tags = [t.strip() for t in industry_tags.strip('[]').split(',') if t.strip()]
                elif industry_tags is None:
                    industry_tags = []

                credit_code = item.get('credit_code')

                # 有 credit_code 时用 ON CONFLICT 实现幂等
                if credit_code:
                    cur.execute("""
                        INSERT INTO companies (
                            company_name, credit_code, registered_capital,
                            capital_amount, established_date, legal_representative,
                            business_scope, registered_address, status,
                            industry_tags, source_url
                        ) VALUES (
                            %(company_name)s, %(credit_code)s, %(registered_capital)s,
                            %(capital_amount)s, %(established_date)s, %(legal_representative)s,
                            %(business_scope)s, %(registered_address)s, %(status)s,
                            %(industry_tags)s, %(source_url)s
                        )
                        ON CONFLICT (credit_code) DO UPDATE SET
                            company_name = EXCLUDED.company_name,
                            registered_capital = EXCLUDED.registered_capital,
                            capital_amount = EXCLUDED.capital_amount,
                            established_date = EXCLUDED.established_date,
                            legal_representative = EXCLUDED.legal_representative,
                            business_scope = EXCLUDED.business_scope,
                            registered_address = EXCLUDED.registered_address,
                            industry_tags = EXCLUDED.industry_tags,
                            source_url = EXCLUDED.source_url,
                            updated_at = NOW()
                        RETURNING (xmax = 0) AS is_insert
                    """, {
                        'company_name': item.get('company_name'),
                        'credit_code': credit_code,
                        'registered_capital': item.get('registered_capital'),
                        'capital_amount': item.get('capital_amount'),
                        'established_date': item.get('established_date') or None,
                        'legal_representative': item.get('legal_representative'),
                        'business_scope': item.get('business_scope'),
                        'registered_address': item.get('registered_address'),
                        'status': item.get('status', 'raw'),
                        'industry_tags': industry_tags if industry_tags else None,
                        'source_url': item.get('source_url'),
                    })

                    result = cur.fetchone()
                    if result and result[0]:
                        self.insert_count += 1
                    else:
                        self.update_count += 1

                else:
                    # 无 credit_code，仅插入 (无法去重)
                    cur.execute("""
                        INSERT INTO companies (
                            company_name, registered_capital,
                            capital_amount, established_date, legal_representative,
                            business_scope, registered_address, status,
                            industry_tags, source_url
                        ) VALUES (
                            %(company_name)s, %(registered_capital)s,
                            %(capital_amount)s, %(established_date)s, %(legal_representative)s,
                            %(business_scope)s, %(registered_address)s, %(status)s,
                            %(industry_tags)s, %(source_url)s
                        )
                    """, {
                        'company_name': item.get('company_name'),
                        'registered_capital': item.get('registered_capital'),
                        'capital_amount': item.get('capital_amount'),
                        'established_date': item.get('established_date') or None,
                        'legal_representative': item.get('legal_representative'),
                        'business_scope': item.get('business_scope'),
                        'registered_address': item.get('registered_address'),
                        'status': item.get('status', 'raw'),
                        'industry_tags': industry_tags if industry_tags else None,
                        'source_url': item.get('source_url'),
                    })
                    self.insert_count += 1

                # 批量提交
                self._pending += 1
                if self._pending >= self._batch_size:
                    self.conn.commit()
                    self._pending = 0

        except psycopg2.errors.UniqueViolation:
            # 极端并发下 credit_code 重复，回滚当前事务继续
            self.conn.rollback()
            logger.debug(f"credit_code 重复跳过: {item.get('credit_code')}")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"数据库写入失败: {e}, company={item.get('company_name')}")

    # ================================================================
    # 格式标准化
    # ================================================================

    @staticmethod
    def _parse_capital(text) -> float:
        """注册资本文本 -> 万元数值"""
        if not text:
            return None
        text = str(text)
        num_match = re.search(r'[\d.]+', text)
        if not num_match:
            return None
        amount = float(num_match.group())
        if '亿' in text:
            amount *= 10000
        elif '万' not in text:
            amount /= 10000
        return round(amount, 2)

    @staticmethod
    def _parse_date(text):
        """日期格式标准化 -> YYYY-MM-DD"""
        if not text:
            return None
        text = str(text).strip()

        # 尝试多种日期格式
        patterns = [
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', '{:04d}-{:02d}-{:02d}'),   # 2020年1月15日
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', '{:04d}-{:02d}-{:02d}'),       # 2020-01-15
            (r'(\d{4})/(\d{1,2})/(\d{1,2})', '{:04d}-{:02d}-{:02d}'),       # 2020/01/15
            (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', '{:04d}-{:02d}-{:02d}'),     # 2020.01.15
        ]

        for pattern, fmt in patterns:
            match = re.search(pattern, text)
            if match:
                y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                try:
                    return fmt.format(y, m, d)
                except (ValueError, OverflowError):
                    continue

        # 无法解析则返回原始文本
        return text
