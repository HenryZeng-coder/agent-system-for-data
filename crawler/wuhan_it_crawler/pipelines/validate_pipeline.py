"""④ 完整性验证管道"""

import re
import logging
from scrapy.exceptions import DropItem

from wuhan_it_crawler.items import CompanyItem, BiddingItem, RecruitmentItem, NewsMentionItem

logger = logging.getLogger(__name__)


class ValidatePipeline:
    """关键字段完整性验证"""

    CREDIT_CODE_PATTERN = re.compile(r'^[0-9A-Z]{18}$')

    def process_item(self, item, spider):
        # CompanyItem: company_name 必须非空
        if isinstance(item, CompanyItem):
            if not item.get('company_name'):
                logger.warning(f"缺少企业名称，丢弃")
                raise DropItem("缺少企业名称")
            credit_code = item.get('credit_code')
            if credit_code and not self.CREDIT_CODE_PATTERN.match(credit_code):
                logger.warning(f"信用代码格式异常: {credit_code} ({item.get('company_name')})")
                item['credit_code'] = None

        # BiddingItem: project_name 必须非空，company_name 可选
        elif isinstance(item, BiddingItem):
            if not item.get('project_name'):
                logger.warning(f"缺少项目名称，丢弃")
                raise DropItem("缺少项目名称")

        # RecruitmentItem: position_title 必须非空
        elif isinstance(item, RecruitmentItem):
            if not item.get('position_title'):
                logger.warning(f"缺少岗位名称，丢弃")
                raise DropItem("缺少岗位名称")

        # NewsMentionItem: title 必须非空
        elif isinstance(item, NewsMentionItem):
            if not item.get('title'):
                logger.warning(f"缺少新闻标题，丢弃")
                raise DropItem("缺少新闻标题")

        return item
