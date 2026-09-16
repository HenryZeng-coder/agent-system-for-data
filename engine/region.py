"""区域范围 — 全国 / 省 / 市 三级采集口径

config/config.yaml 的 region 段决定采集口径：

    region:
      scope: national        # national(全国) | province(按省) | city(按市)
      province: ""           # scope=province|city 时必填, 如 湖北
      city: ""               # scope=city 时必填, 如 武汉
      local_domains: []      # 可选, 本地行业/招投标站点域名

对外只暴露一个概念: **地域词(terms)** 与 **搜索词前缀(prefix)**。

    national → prefix ""         terms ()                       不加任何地域限制
    province → prefix "湖北"      terms ("湖北", "湖北省")
    city     → prefix "武汉"      terms ("武汉", "武汉市", "湖北", "湖北省")

把 scope 设成 city + province=湖北 + city=武汉, 即得到原武汉版的等价行为。
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

_LEVEL_SUFFIXES = ("自治区", "特别行政区", "省", "市")

# 企业名后缀 (与项目原有的名称提取口径保持一致)
_NAME_SUFFIX = r"(?:有限公司|股份有限公司|集团|工作室|研究院|中心)"


def bare(name: str) -> str:
    """去掉行政级别后缀: 武汉市 → 武汉"""
    n = (name or "").strip()
    for s in _LEVEL_SUFFIXES:
        if n.endswith(s) and len(n) > len(s):
            return n[: -len(s)]
    return n


def _dedup(items: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(i for i in items if i))


class Region:
    """采集范围 (不可变语义, 构造后只读)"""

    def __init__(self, scope: str = "national", province: str = "",
                 city: str = "", local_domains: Optional[Sequence[str]] = None):
        scope = (scope or "national").strip().lower()
        self.scope = scope if scope in ("national", "province", "city") else "national"
        self.province = (province or "").strip()
        self.city = (city or "").strip()
        self.local_domains = list(local_domains or [])

    # ---------------- 构造 ----------------

    @classmethod
    def from_config(cls, path: str = "config/config.yaml") -> "Region":
        """从 config.yaml 读取 region 段 (读不到则退回全国)"""
        cfg = {}
        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                cfg = ((yaml.safe_load(f) or {}).get("region") or {})
        except Exception:  # 配置缺失/不可读 → 全国模式, 不阻断采集
            pass
        return cls.from_dict(cfg)

    @classmethod
    def from_dict(cls, cfg: Optional[dict]) -> "Region":
        cfg = cfg or {}
        return cls(cfg.get("scope", "national"), cfg.get("province", ""),
                   cfg.get("city", ""), cfg.get("local_domains"))

    @classmethod
    def from_settings(cls, settings) -> "Region":
        """从 Scrapy settings 读取 (settings.py 已注入 REGION_* 键)"""
        return cls(settings.get("REGION_SCOPE", "national"),
                   settings.get("REGION_PROVINCE", ""),
                   settings.get("REGION_CITY", ""),
                   settings.get("REGION_LOCAL_DOMAINS", []))

    # ---------------- 派生属性 ----------------

    @property
    def names(self) -> List[str]:
        """范围内的地域名(去后缀), 由小到大: [市, 省]"""
        if self.scope == "city" and self.city:
            return _dedup([bare(self.city), bare(self.province)])
        if self.scope == "province" and self.province:
            return [bare(self.province)]
        return []

    @property
    def terms(self) -> Tuple[str, ...]:
        """地域词全集(含行政后缀), 用于地址/企业名匹配"""
        forms: List[str] = []
        if self.scope in ("city", "province") and self.city:
            c = bare(self.city)
            forms += [c, c + "市"]
        if self.scope in ("city", "province") and self.province:
            p = bare(self.province)
            forms += [p, p + "省"]
        return tuple(_dedup(forms))

    @property
    def prefix(self) -> str:
        """搜索词前缀 — 全国模式为空串"""
        names = self.names
        return names[0] if names else ""

    @property
    def label(self) -> str:
        if self.scope == "city" and self.city:
            return f"{bare(self.city)}市"
        if self.scope == "province" and self.province:
            return f"{bare(self.province)}省"
        return "全国"

    @property
    def is_national(self) -> bool:
        return not self.terms

    # ---------------- 搜索词 ----------------

    def query(self, *parts: str) -> str:
        """拼搜索词: 带地域前缀(如有), 自动跳过空片段"""
        return " ".join(p for p in (self.prefix, *parts) if p)

    def queries(self, *parts: str) -> List[str]:
        return [self.query(*parts)]

    # ---------------- 文本匹配 ----------------

    def strip_local(self, text: str) -> str:
        """剥离地域词 — 用于从企业全名派生简称"""
        out = text or ""
        for t in self.terms:
            out = out.replace(t, "")
        return out

    def is_local(self, text: str) -> bool:
        """文本是否属于本范围 — 全国模式恒为 True (不做地域过滤)"""
        if self.is_national:
            return True
        return any(t in (text or "") for t in self.terms)

    def company_name_pattern(self) -> str:
        """企业名提取正则 — 有地域时要求地域前缀, 全国模式不限地域"""
        if self.terms:
            loc = "(?:" + "|".join(re.escape(t) for t in self.terms) + ")"
            return r"(" + loc + r"[^\s,，、|/<>\"]{2,25}" + _NAME_SUFFIX + r")"
        return r"([\u4e00-\u9fa5A-Za-z0-9][^\s,，、|/<>\"]{2,25}" + _NAME_SUFFIX + r")"

    def address_pattern(self) -> str:
        """注册地址回退正则 — 有地域时锚定地域, 全国模式匹配任意省市开头"""
        if self.terms:
            loc = "(?:" + "|".join(re.escape(t) for t in self.terms) + ")"
            return r"(" + loc + r"[^\s,，。]{5,60}?(?:号|路|大道|街|区))"
        return (r"((?:[\u4e00-\u9fa5]{2,8}(?:省|自治区|市))"
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,60}?(?:号|路|大道|街|区))")

    def looks_like_address(self, text: str) -> bool:
        """地址有效性判断

        - 全国模式: 含「市/省/区」任一即可 (不限定具体省市)
        - 省市模式: 命中本地域词即通过; 另保留原武汉版的宽松回退「含『市』」,
          因为注册地址常省略省名 — 这是有意为之, 与改造前逻辑一致。
        """
        t = text or ""
        if self.is_national:
            return bool(t) and ("市" in t or "省" in t or "区" in t)
        return self.is_local(t) or "市" in t

    def bidding_keywords(self, industries: Optional[Sequence[str]] = None) -> List[str]:
        """招投标搜索关键词 — 全国模式为纯行业词, 本地模式加地域前缀"""
        industries = industries or ["信息化", "数字化", "AI", "人工智能",
                                    "云计算", "大数据", "智慧城市", "软件开发"]
        keywords = []
        for ind in industries:
            keywords.append(self.query(ind, "招标"))
            keywords.append(self.query(ind, "采购"))
        if not self.is_national:
            keywords += [self.query("政务云", "中标"), self.query("信创", "采购"),
                         self.query("数字政府", "招标"), self.query("国资云", "招标")]
        return keywords

    def describe(self) -> str:
        return (f"范围={self.label} scope={self.scope} "
                f"prefix='{self.prefix}' terms={list(self.terms)} "
                f"domains={self.local_domains}")


def current(path: str = "config/config.yaml") -> Region:
    """便捷入口: 读取当前配置的区域"""
    return Region.from_config(path)


__all__ = ["Region", "bare", "current"]
