"""② IT行业过滤管道"""

import logging

logger = logging.getLogger(__name__)

IT_KEYWORDS = [
    "软件", "信息技术", "科技", "数据", "互联网",
    "云计算", "人工智能", "智能", "IT", "数字化",
]


class FilterPipeline:
    """IT行业关键词过滤 — 非IT企业丢弃"""

    def process_item(self, item, spider):
        scope = item.get('business_scope', '') or ''
        tags = item.get('industry_tags', []) or []

        text = scope + ' '.join(tags) if isinstance(tags, list) else scope + str(tags)

        if not any(kw in text for kw in IT_KEYWORDS):
            logger.debug(f"非IT企业过滤: {item.get('company_name')}")
            from .dedup_pipeline import DropItem
            raise DropItem(f"非IT企业: {item.get('company_name')}")

        return item
