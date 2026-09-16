"""⑤ 格式标准化管道 + 数据库写入"""

import re
import logging
import psycopg2
from datetime import datetime

from cn_it_crawler.items import (
    CompanyItem, TechProfileItem, RecruitmentItem,
    NewsMentionItem, BiddingItem, CrawlTaskItem,
)

logger = logging.getLogger(__name__)

# 数据库字段长度上限 (与 init.sql 的 VARCHAR 定义保持一致)
MAX_TITLE_LEN = 500          # news_mentions.title
MAX_PROJECT_NAME_LEN = 500   # bidding_records.project_name


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
        """类型分发: 根据 Item 类型路由到对应处理方法"""
        if isinstance(item, CompanyItem):
            return self._process_company(item)
        elif isinstance(item, TechProfileItem):
            return self._process_tech_profile(item)
        elif isinstance(item, RecruitmentItem):
            return self._process_recruitment(item)
        elif isinstance(item, NewsMentionItem):
            return self._process_news_mention(item)
        elif isinstance(item, BiddingItem):
            return self._process_bidding(item)
        elif isinstance(item, CrawlTaskItem):
            return self._process_crawl_task(item)
        return item

    # ================================================================
    # CompanyItem 处理
    # ================================================================

    def _process_company(self, item):
        """原逻辑: 金额/日期标准化 + 写入 companies 表"""
        item['capital_amount'] = self._parse_capital(item.get('registered_capital'))
        if item.get('established_date') and isinstance(item['established_date'], str):
            item['established_date'] = self._parse_date(item['established_date'])
        item['status'] = 'raw'
        self._write_company_to_db(item)
        return item

    def _write_company_to_db(self, item):
        """写入 companies 表，使用 ON CONFLICT 实现幂等"""
        try:
            with self.conn.cursor() as cur:
                industry_tags = item.get('industry_tags')
                if isinstance(industry_tags, str):
                    industry_tags = [t.strip() for t in industry_tags.strip('[]').split(',') if t.strip()]
                elif industry_tags is None:
                    industry_tags = []

                credit_code = item.get('credit_code')

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

                self._batch_commit()

        except psycopg2.errors.UniqueViolation:
            self.conn.rollback()
            logger.debug(f"credit_code 重复跳过: {item.get('credit_code')}")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"数据库写入失败: {e}, company={item.get('company_name')}")

    # ================================================================
    # TechProfileItem 处理
    # ================================================================

    def _process_tech_profile(self, item):
        tech_stack = item.get('tech_stack')
        if isinstance(tech_stack, str):
            tech_stack = [t.strip() for t in tech_stack.strip('[]').split(',') if t.strip()]
            item['tech_stack'] = tech_stack
        item['github_stars'] = int(item.get('github_stars') or 0)
        item['has_github_org'] = bool(item.get('github_org'))
        item['has_tech_blog'] = bool(item.get('tech_blog_url'))
        item['ai_job_ratio'] = float(item.get('ai_job_ratio') or 0.0)
        self._write_tech_profile_to_db(item)
        return item

    def _write_tech_profile_to_db(self, item):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tech_profiles (
                        company_id, tech_stack, github_org, github_stars,
                        tech_blog_url, cloud_provider, has_github_org,
                        has_tech_blog, ai_job_ratio
                    ) VALUES (
                        %(company_id)s, %(tech_stack)s, %(github_org)s,
                        %(github_stars)s, %(tech_blog_url)s, %(cloud_provider)s,
                        %(has_github_org)s, %(has_tech_blog)s, %(ai_job_ratio)s
                    )
                    ON CONFLICT (company_id) DO UPDATE SET
                        tech_stack = EXCLUDED.tech_stack,
                        github_org = EXCLUDED.github_org,
                        github_stars = EXCLUDED.github_stars,
                        tech_blog_url = EXCLUDED.tech_blog_url,
                        cloud_provider = EXCLUDED.cloud_provider,
                        has_github_org = EXCLUDED.has_github_org,
                        has_tech_blog = EXCLUDED.has_tech_blog,
                        ai_job_ratio = EXCLUDED.ai_job_ratio
                """, {
                    'company_id': item.get('company_id'),
                    'tech_stack': item.get('tech_stack') or None,
                    'github_org': item.get('github_org') or None,
                    'github_stars': item.get('github_stars', 0),
                    'tech_blog_url': item.get('tech_blog_url') or None,
                    'cloud_provider': item.get('cloud_provider') or None,
                    'has_github_org': item.get('has_github_org', False),
                    'has_tech_blog': item.get('has_tech_blog', False),
                    'ai_job_ratio': item.get('ai_job_ratio', 0.0),
                })
                self.insert_count += 1
                self._batch_commit()
        except psycopg2.errors.UniqueViolation:
            self.conn.rollback()
            logger.debug(f"tech_profile 重复跳过: company_id={item.get('company_id')}")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"tech_profiles 写入失败: {e}, company_id={item.get('company_id')}")

    # ================================================================
    # RecruitmentItem 处理
    # ================================================================

    def _process_recruitment(self, item):
        item['salary_min'] = int(item['salary_min']) if item.get('salary_min') else None
        item['salary_max'] = int(item['salary_max']) if item.get('salary_max') else None
        item['headcount'] = int(item.get('headcount') or 1)
        tech_keywords = item.get('tech_keywords')
        if isinstance(tech_keywords, str):
            tech_keywords = [t.strip() for t in tech_keywords.strip('[]').split(',') if t.strip()]
            item['tech_keywords'] = tech_keywords
        self._write_recruitment_to_db(item)
        return item

    def _write_recruitment_to_db(self, item):
        company_id = item.get('company_id')
        if not company_id:
            logger.warning(f"招聘记录缺少 company_id，跳过: {item.get('position_title')}")
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO recruitments (
                        company_id, position_title, salary_range,
                        salary_min, salary_max, tech_keywords,
                        headcount, source_url, source_name
                    ) VALUES (
                        %(company_id)s, %(position_title)s, %(salary_range)s,
                        %(salary_min)s, %(salary_max)s, %(tech_keywords)s,
                        %(headcount)s, %(source_url)s, %(source_name)s
                    )
                    ON CONFLICT (company_id, position_title, source_name) DO NOTHING
                """, {
                    'company_id': company_id,
                    'position_title': item.get('position_title'),
                    'salary_range': item.get('salary_range'),
                    'salary_min': item.get('salary_min'),
                    'salary_max': item.get('salary_max'),
                    'tech_keywords': item.get('tech_keywords') or None,
                    'headcount': item.get('headcount', 1),
                    'source_url': item.get('source_url'),
                    'source_name': item.get('source_name'),
                })
                self.insert_count += 1
                self._batch_commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"recruitments 写入失败: {e}, title={item.get('position_title')}")

    # ================================================================
    # NewsMentionItem 处理
    # ================================================================

    def _process_news_mention(self, item):
        if item.get('published_at') and isinstance(item['published_at'], str):
            item['published_at'] = self._parse_date(item['published_at'])
        item['sentiment_score'] = float(item.get('sentiment_score') or 0.0)
        item['relevance_score'] = float(item.get('relevance_score') or 0.0)
        item['is_digital_related'] = bool(item.get('is_digital_related'))
        # title 超长截断, 避免 VARCHAR(500) 写入失败
        title = item.get('title', '') or ''
        if len(title) > MAX_TITLE_LEN:
            item['title'] = title[:MAX_TITLE_LEN]
            logger.debug(f"新闻标题截断: {len(title)} -> {MAX_TITLE_LEN}")
        self._write_news_mention_to_db(item)
        return item

    def _write_news_mention_to_db(self, item):
        company_id = item.get('company_id')
        if not company_id:
            logger.warning(f"新闻记录缺少 company_id，跳过: {item.get('title')}")
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO news_mentions (
                        company_id, title, content_summary,
                        source_url, source_name, published_at,
                        sentiment_score, relevance_score, is_digital_related
                    ) VALUES (
                        %(company_id)s, %(title)s, %(content_summary)s,
                        %(source_url)s, %(source_name)s, %(published_at)s,
                        %(sentiment_score)s, %(relevance_score)s, %(is_digital_related)s
                    )
                    ON CONFLICT (company_id, title, source_name) DO NOTHING
                """, {
                    'company_id': company_id,
                    'title': item.get('title'),
                    'content_summary': item.get('content_summary'),
                    'source_url': item.get('source_url'),
                    'source_name': item.get('source_name'),
                    'published_at': item.get('published_at') or None,
                    'sentiment_score': item.get('sentiment_score', 0.0),
                    'relevance_score': item.get('relevance_score', 0.0),
                    'is_digital_related': item.get('is_digital_related', False),
                })
                self.insert_count += 1
                self._batch_commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"news_mentions 写入失败: {e}, title={item.get('title')}")

    # ================================================================
    # BiddingItem 处理
    # ================================================================

    def _process_bidding(self, item):
        item['budget_amount'] = float(item['budget_amount']) if item.get('budget_amount') else None
        item['is_digital'] = bool(item.get('is_digital'))
        if item.get('bid_date') and isinstance(item['bid_date'], str):
            item['bid_date'] = self._parse_date(item['bid_date'])
        # project_name 超长截断, 避免 VARCHAR(500) 写入失败
        project_name = item.get('project_name', '') or ''
        if len(project_name) > MAX_PROJECT_NAME_LEN:
            item['project_name'] = project_name[:MAX_PROJECT_NAME_LEN]
            logger.debug(f"招标项目名截断: {len(project_name)} -> {MAX_PROJECT_NAME_LEN}")
        self._write_bidding_to_db(item)
        return item

    def _write_bidding_to_db(self, item):
        company_id = item.get('company_id')
        if not company_id:
            logger.warning(f"招投标记录缺少 company_id, 仍写入: {item.get('project_name')}")
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bidding_records (
                        company_id, project_name, project_type,
                        budget_amount, is_digital, bid_date,
                        source_url, source_name
                    ) VALUES (
                        %(company_id)s, %(project_name)s, %(project_type)s,
                        %(budget_amount)s, %(is_digital)s, %(bid_date)s,
                        %(source_url)s, %(source_name)s
                    )
                    ON CONFLICT (company_id, project_name, source_name) DO NOTHING
                """, {
                    'company_id': company_id,
                    'project_name': item.get('project_name'),
                    'project_type': item.get('project_type'),
                    'budget_amount': item.get('budget_amount'),
                    'is_digital': item.get('is_digital', False),
                    'bid_date': item.get('bid_date') or None,
                    'source_url': item.get('source_url'),
                    'source_name': item.get('source_name'),
                })
                self.insert_count += 1
                self._batch_commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"bidding_records 写入失败: {e}, project={item.get('project_name')}")

    # ================================================================
    # CrawlTaskItem 处理
    # ================================================================

    def _process_crawl_task(self, item):
        item['priority'] = int(item.get('priority') or 5)
        item['status'] = item.get('status') or 'pending'
        self._write_crawl_task_to_db(item)
        return item

    def _write_crawl_task_to_db(self, item):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO crawl_tasks (
                        task_type, source_name, target_url,
                        priority, status, retry_count, result_summary
                    ) VALUES (
                        %(task_type)s, %(source_name)s, %(target_url)s,
                        %(priority)s, %(status)s, %(retry_count)s, %(result_summary)s
                    )
                """, {
                    'task_type': item.get('task_type'),
                    'source_name': item.get('source_name'),
                    'target_url': item.get('target_url'),
                    'priority': item.get('priority', 5),
                    'status': item.get('status', 'pending'),
                    'retry_count': int(item.get('retry_count') or 0),
                    'result_summary': item.get('result_summary'),
                })
                self.insert_count += 1
                self._batch_commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"crawl_tasks 写入失败: {e}")

    # ================================================================
    # 通用工具方法
    # ================================================================

    def _batch_commit(self):
        """批量提交"""
        self._pending += 1
        if self._pending >= self._batch_size:
            self.conn.commit()
            self._pending = 0

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

        patterns = [
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', '{:04d}-{:02d}-{:02d}'),
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', '{:04d}-{:02d}-{:02d}'),
            (r'(\d{4})/(\d{1,2})/(\d{1,2})', '{:04d}-{:02d}-{:02d}'),
            (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', '{:04d}-{:02d}-{:02d}'),
        ]

        for pattern, fmt in patterns:
            match = re.search(pattern, text)
            if match:
                y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                try:
                    return fmt.format(y, m, d)
                except (ValueError, OverflowError):
                    continue

        return text
