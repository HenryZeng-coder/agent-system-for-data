"""④ 完整性验证管道 — 真实性增强

在原有"必填字段非空"基础上新增:
1. 统一社会信用代码: 18位格式 + GB 32100-2015 校验和算法
2. 成立日期: 合法日期 + 不晚于今天 + 不早于1980
3. 注册资本: 数值 > 0 且不超合理上限
4. 企业名称: 拦截明显噪声 (搜索词/截断文本)
5. 招聘薪资: salary_min <= salary_max 且为正数
6. 新闻日期: 不晚于未来
7. 招投标金额: > 0

原则: 格式/合理性异常 → 置空该字段并警告, 不丢弃整条 (除必填缺失)。
"""

import re
import logging
from datetime import datetime, date
from scrapy.exceptions import DropItem

from wuhan_it_crawler.items import CompanyItem, BiddingItem, RecruitmentItem, NewsMentionItem

logger = logging.getLogger(__name__)


class ValidatePipeline:
    """关键字段完整性 + 真实性验证"""

    CREDIT_CODE_PATTERN = re.compile(r'^[0-9A-Z]{18}$')

    # GB 32100-2015: 前17位加权因子
    _WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
    # 校验字符表 (不含 I/O/S/V/Z)
    _CHECK_CHARS = '0123456789ABCDEFGHJKLMNPQRTUWXY'

    # 成立日期合理范围
    MIN_ESTABLISHED_YEAR = 1980

    # 注册资本上限 (万元): 1000亿 — 超出视为数据异常
    MAX_CAPITAL_WAN = 10_000_000

    # 企业名称噪声词 — 明显非公司名的片段
    NAME_NOISE_KEYWORDS = ['搜索', '结果', '推荐', '更多', '下一页', '相关',
                           '百度', '搜狗', '必应', '新闻', '招聘', '点击', '查看']

    # 企业名称合法后缀 (含这些后缀视为完整公司名)
    NAME_LEGAL_SUFFIXES = ('公司', '集团', '中心', '研究院', '研究所', '工作室',
                           '事务所', '合作社', '银行', '学院', '大学', '厂', '店')

    def process_item(self, item, spider):
        # CompanyItem: company_name 必须非空
        if isinstance(item, CompanyItem):
            return self._validate_company(item)

        # BiddingItem: project_name 必须非空
        elif isinstance(item, BiddingItem):
            if not item.get('project_name'):
                logger.warning(f"缺少项目名称，丢弃")
                raise DropItem("缺少项目名称")
            self._validate_budget(item)
            return item

        # RecruitmentItem: position_title 必须非空
        elif isinstance(item, RecruitmentItem):
            if not item.get('position_title'):
                logger.warning(f"缺少岗位名称，丢弃")
                raise DropItem("缺少岗位名称")
            self._validate_salary(item)
            return item

        # NewsMentionItem: title 必须非空
        elif isinstance(item, NewsMentionItem):
            if not item.get('title'):
                logger.warning(f"缺少新闻标题，丢弃")
                raise DropItem("缺少新闻标题")
            self._validate_news_date(item)
            return item

        return item

    # ================================================================
    # CompanyItem 验证
    # ================================================================

    def _validate_company(self, item):
        name = item.get('company_name')
        if not name:
            logger.warning(f"缺少企业名称，丢弃")
            raise DropItem("缺少企业名称")

        # 名称噪声拦截: 名称不含合法后缀 且 含噪声词 → 丢弃
        if self._is_noise_name(name):
            logger.warning(f"企业名称疑似噪声, 丢弃: {name}")
            raise DropItem(f"企业名称疑似噪声: {name}")

        # 信用代码: 格式 + GB32100 校验和 → 异常置空
        credit_code = item.get('credit_code')
        if credit_code and not self.is_valid_credit_code(credit_code):
            logger.warning(
                f"信用代码校验失败, 置空: {credit_code} ({item.get('company_name')})"
            )
            item['credit_code'] = None

        # 成立日期合理性
        self._validate_established_date(item)

        # 注册资本合理性
        self._validate_capital(item)

        return item

    def _is_noise_name(self, name: str) -> bool:
        """判断名称是否为明显噪声 (搜索词片段/截断文本)"""
        name = str(name).strip()
        if len(name) < 2:
            return True
        # 含噪声词 且 不含合法公司后缀
        has_noise = any(kw in name for kw in self.NAME_NOISE_KEYWORDS)
        has_suffix = name.endswith(self.NAME_LEGAL_SUFFIXES)
        return has_noise and not has_suffix

    def _validate_established_date(self, item):
        """成立日期: 合法日期 + 不晚于今天 + 不早于1980 → 异常置空"""
        est = item.get('established_date')
        if not est:
            return
        try:
            # 兼容 "2020-01-15" / "2020年1月15日" / datetime/date 对象
            if isinstance(est, (datetime, date)):
                d = est.date() if isinstance(est, datetime) else est
            else:
                text = str(est).strip()
                m = re.match(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})', text)
                if not m:
                    item['established_date'] = None
                    return
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

            today = date.today()
            if d > today:
                logger.warning(f"成立日期晚于今天, 置空: {est}")
                item['established_date'] = None
            elif d.year < self.MIN_ESTABLISHED_YEAR:
                logger.warning(f"成立日期过早(>{self.MIN_ESTABLISHED_YEAR}), 置空: {est}")
                item['established_date'] = None
        except (ValueError, TypeError):
            logger.warning(f"成立日期非法, 置空: {est}")
            item['established_date'] = None

    def _validate_capital(self, item):
        """注册资本: > 0 且不超上限 → 异常置空"""
        capital = item.get('capital_amount')
        if capital is None:
            return
        try:
            amount = float(capital)
        except (ValueError, TypeError):
            logger.warning(f"注册资本非数值, 置空: {capital}")
            item['capital_amount'] = None
            return
        if amount <= 0 or amount > self.MAX_CAPITAL_WAN:
            logger.warning(f"注册资本超合理范围, 置空: {capital}")
            item['capital_amount'] = None

    # ================================================================
    # RecruitmentItem / NewsMentionItem / BiddingItem 验证
    # ================================================================

    def _validate_salary(self, item):
        """薪资区间: min <= max 且为正数 → 异常置空"""
        lo, hi = item.get('salary_min'), item.get('salary_max')
        if lo is None and hi is None:
            return
        try:
            lo = float(lo) if lo is not None else None
            hi = float(hi) if hi is not None else None
        except (ValueError, TypeError):
            item['salary_min'] = item['salary_max'] = None
            return

        invalid = False
        if lo is not None and lo <= 0:
            invalid = True
        if hi is not None and hi <= 0:
            invalid = True
        if lo is not None and hi is not None and lo > hi:
            invalid = True
        if invalid:
            logger.warning(
                f"薪资区间不合理, 置空: {lo}-{hi} ({item.get('position_title')})"
            )
            item['salary_min'] = item['salary_max'] = None

    def _validate_news_date(self, item):
        """新闻发布日期: 不晚于未来 → 异常置空"""
        pub = item.get('published_at')
        if not pub:
            return
        try:
            if isinstance(pub, (datetime, date)):
                d = pub.date() if isinstance(pub, datetime) else pub
            else:
                text = str(pub).strip()
                m = re.match(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})', text)
                if not m:
                    return  # 无法解析则不处理 (留给 standardize)
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d > date.today():
                logger.warning(f"新闻发布日期晚于今天, 置空: {pub}")
                item['published_at'] = None
        except (ValueError, TypeError):
            pass

    def _validate_budget(self, item):
        """招投标预算: > 0 → 异常置空"""
        budget = item.get('budget_amount')
        if budget is None:
            return
        try:
            amount = float(budget)
        except (ValueError, TypeError):
            item['budget_amount'] = None
            return
        if amount <= 0:
            logger.warning(f"招标预算非正数, 置空: {budget}")
            item['budget_amount'] = None

    # ================================================================
    # GB 32100-2015 统一社会信用代码校验和
    # ================================================================

    @classmethod
    def is_valid_credit_code(cls, code: str) -> bool:
        """验证18位统一社会信用代码 (格式 + 校验和)

        算法: 前17位字符映射数字(0-9不变, A-Z=10-35),
        与权重因子(1,3,9,27,...)加权求和, mod 31,
        余数映射到校验字符表, 与第18位比对。
        """
        if not code or not cls.CREDIT_CODE_PATTERN.match(code):
            return False

        total = 0
        for i, ch in enumerate(code[:17]):
            if ch.isdigit():
                v = int(ch)
            else:
                v = ord(ch) - ord('A') + 10
            total += v * cls._WEIGHTS[i]

        check_index = (31 - total % 31) % 31
        return cls._CHECK_CHARS[check_index] == code[17]

    @classmethod
    def calculate_check_char(cls, first17: str) -> str:
        """根据前17位计算校验字符 (测试/生成用)"""
        if not first17 or len(first17) != 17:
            raise ValueError("需要恰好17位字符")
        total = 0
        for i, ch in enumerate(first17):
            if ch.isdigit():
                v = int(ch)
            else:
                v = ord(ch) - ord('A') + 10
            total += v * cls._WEIGHTS[i]
        check_index = (31 - total % 31) % 31
        return cls._CHECK_CHARS[check_index]
