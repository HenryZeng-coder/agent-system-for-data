"""④ 完整性验证管道"""

import re
import logging
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class ValidatePipeline:
    """关键字段完整性验证"""

    CREDIT_CODE_PATTERN = re.compile(r'^[0-9A-HJ-NP-RTUW-Y]{2}\d{6}[0-9A-HJ-NP-RTUW-Y]{10}$')

    def process_item(self, item, spider):
        # company_name 必须非空
        if not item.get('company_name'):
            logger.warning(f"缺少企业名称，丢弃")
            raise DropItem("缺少企业名称")

        # credit_code 格式校验 (可选但必须合规)
        credit_code = item.get('credit_code')
        if credit_code and not self.CREDIT_CODE_PATTERN.match(credit_code):
            logger.warning(f"信用代码格式异常: {credit_code} ({item.get('company_name')})")
            item['credit_code'] = None  # 格式不对则置空

        return item
