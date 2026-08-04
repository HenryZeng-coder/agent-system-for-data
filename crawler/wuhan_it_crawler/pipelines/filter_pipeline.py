"""② IT行业过滤管道"""

import logging
from scrapy.exceptions import DropItem
from wuhan_it_crawler.items import CompanyItem

logger = logging.getLogger(__name__)

IT_KEYWORDS = [
    "软件", "信息技术", "科技", "数据", "互联网",
    "云计算", "人工智能", "智能", "IT", "数字化",
]


class FilterPipeline:
    """IT行业关键词过滤 — 仅对 CompanyItem 执行，其他类型直接放行"""

    def process_item(self, item, spider):
        # 只有 CompanyItem 才执行 IT 关键词过滤
        if not isinstance(item, CompanyItem):
            return item

        scope = item.get('business_scope', '') or ''
        tags = item.get('industry_tags', []) or []

        text = scope + ' '.join(tags) if isinstance(tags, list) else scope + str(tags)

        if not any(kw in text for kw in IT_KEYWORDS):
            logger.debug(f"非IT企业过滤: {item.get('company_name')}")
            raise DropItem(f"非IT企业: {item.get('company_name')}")

        return item
