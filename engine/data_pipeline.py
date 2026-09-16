"""批量数据处理管道 — 5级处理: 去重→IT行业过滤→清洗→验证→标准化

与 Scrapy 5级 Pipeline (dedup→filter→clean→validate→standardize) 逻辑对齐，
供非 Scrapy 场景（如直接从数据库批量处理）使用。
"""

import re
import logging
import yaml

logger = logging.getLogger(__name__)


class DataPipeline:
    """5级数据处理管道"""

    def __init__(self, config_path: str = "config/scoring_rules.yaml"):
        self.config = self._load_config(config_path)

    @staticmethod
    def _load_config(config_path: str) -> dict:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError):
            return {}

    # ================================================================
    # 1. 去重 (优先级 100)
    # ================================================================

    def deduplicate(self, data: list) -> list:
        """基于 credit_code 去重，保留首次出现的记录

        Args:
            data: dict 列表，每条记录应含 credit_code 字段

        Returns:
            去重后的列表
        """
        if not data:
            return []
        seen = set()
        result = []
        for item in data:
            key = item.get("credit_code")
            if key is None:
                # 无 credit_code 的记录保留
                result.append(item)
                continue
            if key not in seen:
                seen.add(key)
                result.append(item)
            else:
                logger.debug(f"去重: 跳过重复 credit_code={key}")
        logger.info(f"去重: {len(data)} → {len(result)} 条")
        return result

    # ================================================================
    # 2. IT 行业过滤 (优先级 200)
    # ================================================================

    def filter_by_industry(self, data: list) -> list:
        """IT行业关键词过滤 — 从 scoring_rules.yaml 读取 it_filter_keywords

        匹配字段: business_scope, industry_tags
        不匹配则过滤掉。
        """
        keywords = self.config.get("it_filter_keywords", [
            "软件", "信息技术", "科技", "数据", "互联网",
            "云计算", "人工智能", "智能", "IT", "数字化",
        ])
        result = []
        for item in data:
            scope = item.get("business_scope", "") or ""
            tags = item.get("industry_tags", "")
            if isinstance(tags, list):
                tags = " ".join(str(t) for t in tags)
            text = f"{scope} {tags}"
            if any(kw in text for kw in keywords):
                result.append(item)
            else:
                logger.debug(f"过滤: 非IT行业 — {item.get('company_name', '未知')}")
        logger.info(f"行业过滤: {len(data)} → {len(result)} 条")
        return result

    # ================================================================
    # 3. 数据清洗 (优先级 300)
    # ================================================================

    def clean_fields(self, data: list) -> list:
        """数据清洗 — 空值统一、全角转半角、HTML标签清除、多余空白压缩"""
        result = []
        for item in data:
            cleaned = {}
            for k, v in item.items():
                cleaned[k] = self._clean_value(v)
            result.append(cleaned)
        return result

    @staticmethod
    def _clean_value(value):
        """清洗单个值"""
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            return value
        # 全角数字/字母 → 半角
        fullwidth = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        halfwidth = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        value = value.translate(str.maketrans(fullwidth, halfwidth))
        # 清除 HTML 标签
        value = re.sub(r"<[^>]+>", "", value)
        # 多余空白压缩
        value = re.sub(r"\s+", " ", value).strip()
        return value if value else None

    # ================================================================
    # 4. 完整性验证 (优先级 400)
    # ================================================================

    def validate_completeness(self, data: list) -> list:
        """完整性验证 — company_name 必须非空，credit_code 18位格式校验(可选)"""
        result = []
        for item in data:
            name = item.get("company_name")
            if not name:
                logger.debug(f"验证: 缺少 company_name，跳过 — {item}")
                continue
            # credit_code 格式校验: 18位统一社会信用代码 (可选，格式不对置空)
            credit = item.get("credit_code")
            if credit and not re.match(r"^[0-9A-Z]{18}$", str(credit)):
                logger.debug(f"验证: credit_code 格式不对，置空 — {credit}")
                item = dict(item)  # 避免修改原数据
                item["credit_code"] = None
            result.append(item)
        logger.info(f"完整性验证: {len(data)} → {len(result)} 条")
        return result

    # ================================================================
    # 5. 格式标准化 (优先级 500)
    # ================================================================

    def standardize(self, data: list) -> list:
        """格式标准化 — 注册资本文本→万元数值，日期→YYYY-MM-DD"""
        result = []
        for item in data:
            std = dict(item)
            # 注册资本: "5000万元"→5000, "1亿"→10000, "300万"→300
            cap = item.get("capital_amount") or item.get("registered_capital")
            if isinstance(cap, str):
                std["capital_amount"] = self._parse_capital(cap)
            # 日期标准化
            for date_field in ("established_date", "created_at", "updated_at"):
                val = item.get(date_field)
                if isinstance(val, str):
                    std[date_field] = self._standardize_date(val)
            result.append(std)
        return result

    @staticmethod
    def _parse_capital(text: str) -> float:
        """解析注册资本文本为万元数值"""
        m = re.search(r"(\d+\.?\d*)\s*亿", text)
        if m:
            return float(m.group(1)) * 10000
        m = re.search(r"(\d+\.?\d*)\s*万", text)
        if m:
            return float(m.group(1))
        m = re.search(r"(\d+\.?\d*)", text)
        if m:
            return float(m.group(1))
        return 0.0

    @staticmethod
    def _standardize_date(text: str) -> str:
        """日期格式标准化 → YYYY-MM-DD"""
        m = re.search(r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return text

    # ================================================================
    # 全流程执行
    # ================================================================

    def run(self, data: list) -> list:
        """执行完整的5级管道: 去重→过滤→清洗→验证→标准化"""
        data = self.deduplicate(data)
        data = self.filter_by_industry(data)
        data = self.clean_fields(data)
        data = self.validate_completeness(data)
        data = self.standardize(data)
        return data
