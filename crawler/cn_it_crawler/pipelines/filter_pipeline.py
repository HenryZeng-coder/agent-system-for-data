"""② IT行业过滤管道 — 分层关键词匹配

从 config/industry_keywords.yaml 读取分层词库:
  1. 命中 exclude_keywords 且未命中 strong → DropItem (排除词优先)
  2. 命中任一 strong_keywords → 保留
  3. 命中 medium >= 2 个 → 保留
  4. 命中 medium >= 1 且 weak >= 1 → 保留
  5. 否则 DropItem

配置文件缺失时回退到内置词库 (保持向后兼容)。
"""

import os
import logging
from scrapy.exceptions import DropItem
from cn_it_crawler.items import CompanyItem

logger = logging.getLogger(__name__)

# ---- 内置回退词库 (config/industry_keywords.yaml 缺失时使用) ----
_FALLBACK_KEYWORDS = {
    "strong": ["软件", "信息技术", "科技", "数据", "互联网",
               "云计算", "人工智能", "智能", "IT", "数字化"],
    "medium": ["信息化", "智慧", "芯片", "半导体", "机器人",
               "自动化", "嵌入式", "网络", "电子", "通信"],
    "weak": ["技术", "研发", "平台", "系统"],
    "exclude": ["劳务派遣", "家政服务", "餐饮管理", "物业管理",
                "房地产", "建筑工程", "贸易", "物流", "农业"],
}

# 配置路径: 项目根目录 config/industry_keywords.yaml
_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "industry_keywords.yaml"
)


class FilterPipeline:
    """IT行业关键词过滤 — 仅对 CompanyItem 执行，其他类型直接放行"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or _CONFIG_PATH
        self._keywords: dict = dict(_FALLBACK_KEYWORDS)
        self._load_keywords()

    def _load_keywords(self):
        """加载分层词库: 优先 YAML 配置, 缺失回退内置"""
        try:
            import yaml
            with open(self.config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._keywords = {
                "strong": data.get("strong_keywords") or [],
                "medium": data.get("medium_keywords") or [],
                "weak": data.get("weak_keywords") or [],
                "exclude": data.get("exclude_keywords") or [],
            }
            # 校验: 配置为空则回退
            if not any(self._keywords.values()):
                self._keywords = _FALLBACK_KEYWORDS
                logger.warning(f"词库配置为空, 使用内置回退词库: {self.config_path}")
            else:
                logger.info(
                    f"加载分层词库: 强={len(self._keywords['strong'])}, "
                    f"中={len(self._keywords['medium'])}, "
                    f"弱={len(self._keywords['weak'])}, "
                    f"排除={len(self._keywords['exclude'])}"
                )
        except FileNotFoundError:
            self._keywords = _FALLBACK_KEYWORDS
            logger.warning(f"词库配置文件缺失, 使用内置回退词库: {self.config_path}")
        except Exception as e:
            self._keywords = _FALLBACK_KEYWORDS
            logger.warning(f"词库加载失败({e}), 使用内置回退词库")

    def process_item(self, item, spider):
        # 只有 CompanyItem 才执行 IT 关键词过滤
        if not isinstance(item, CompanyItem):
            return item

        scope = item.get('business_scope', '') or ''
        tags = item.get('industry_tags', []) or []
        name = item.get('company_name', '') or ''

        if isinstance(tags, list):
            tag_text = ' '.join(tags)
        else:
            tag_text = str(tags)

        text = f"{scope} {tag_text} {name}"

        decision = self._match(text)
        if not decision:
            logger.debug(f"非IT企业过滤: {item.get('company_name')}")
            raise DropItem(f"非IT企业: {item.get('company_name')}")

        return item

    # ================================================================
    # 分层匹配逻辑
    # ================================================================

    def _match(self, text: str) -> bool:
        """分层判定文本是否属于IT行业"""
        kws = self._keywords
        text_lower = text.lower()

        hit_strong = [kw for kw in kws["strong"] if kw.lower() in text_lower]
        hit_medium = [kw for kw in kws["medium"] if kw.lower() in text_lower]
        hit_weak = [kw for kw in kws["weak"] if kw.lower() in text_lower]
        hit_exclude = [kw for kw in kws["exclude"] if kw.lower() in text_lower]

        # 1) 排除词优先: 命中排除词且未命中强词 → 拒绝
        if hit_exclude and not hit_strong:
            logger.debug(f"排除词命中: {hit_exclude}")
            return False

        # 2) 强词命中 → 保留
        if hit_strong:
            return True

        # 3) 中等词 >= 2 → 保留
        if len(hit_medium) >= 2:
            return True

        # 4) 中等词 >= 1 且 弱词 >= 1 → 保留
        if hit_medium and hit_weak:
            return True

        return False

    # 对外暴露: 供 spider 复用词库打标签
    @property
    def keywords(self) -> dict:
        return self._keywords
