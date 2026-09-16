"""③ 数据清洗管道"""

import re
import logging

logger = logging.getLogger(__name__)


class CleanPipeline:
    """数据清洗: 空值处理/全角半角/HTML标签/编码统一"""

    def process_item(self, item, spider):
        for field in item.fields:
            value = item.get(field)
            if value is None or value == '' or value == 'null':
                item[field] = None
                continue
            if isinstance(value, str):
                item[field] = self._clean_string(value)
        return item

    @staticmethod
    def _clean_string(s: str) -> str:
        # 全角→半角
        s = s.replace('！', '!').replace('，', ',').replace('：', ':')
        s = s.replace('（', '(').replace('）', ')').replace('；', ';')
        # 去除HTML标签
        s = re.sub(r'<[^>]+>', '', s)
        # 去除多余空白
        s = re.sub(r'\s+', ' ', s).strip()
        return s
