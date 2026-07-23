"""代理IP池管理"""

import threading
import time
import requests


class ProxyPool:
    """代理IP池: 获取/验证/剔除/自动切换"""

    MAX_FAILS = 3  # 连续失败次数上限，达到后剔除

    def __init__(self, api_url=None):
        self.api_url = api_url
        self.proxies = []  # [{"url": ..., "fail_count": 0, "last_used": 0}, ...]
        self._lock = threading.Lock()

    # ── 代理获取 ──────────────────────────────────────────────

    def get_proxy(self):
        """获取一个可用代理（最少失败 + 最久未用优先）"""
        with self._lock:
            if not self.proxies:
                return None
            # 过滤掉已被剔除（fail_count >= MAX_FAILS）的代理
            available = [p for p in self.proxies if p["fail_count"] < self.MAX_FAILS]
            if not available:
                return None
            # 排序：最少失败优先，同失败数则最久未用优先
            available.sort(key=lambda p: (p["fail_count"], -p["last_used"]))
            chosen = available[0]
            chosen["last_used"] = time.time()
            return chosen["url"]

    # ── 状态标记 ──────────────────────────────────────────────

    def mark_failed(self, proxy):
        """标记代理失败，连续失败 MAX_FAILS 次后剔除"""
        with self._lock:
            entry = self._find_entry(proxy)
            if entry is None:
                return
            entry["fail_count"] += 1
            if entry["fail_count"] >= self.MAX_FAILS:
                self.proxies.remove(entry)

    def mark_success(self, proxy):
        """标记代理成功，重置失败计数"""
        with self._lock:
            entry = self._find_entry(proxy)
            if entry is None:
                return
            entry["fail_count"] = 0

    # ── 池刷新 ────────────────────────────────────────────────

    def refresh(self):
        """从 API 刷新代理池，兼容常见格式：
        - 列表 ["ip:port", ...]
        - 列表 [{"ip": ..., "port": ...}, ...]
        - 列表 [{"ip": ..., "port": ..., "protocol": ...}, ...]
        """
        if not self.api_url:
            return
        try:
            resp = requests.get(self.api_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return

        new_entries = []
        if isinstance(data, list):
            for item in data:
                url = self._parse_proxy_item(item)
                if url:
                    new_entries.append({
                        "url": url,
                        "fail_count": 0,
                        "last_used": 0,
                    })

        with self._lock:
            # 合入新代理：已存在的保留 fail_count，新代理直接加入
            existing_urls = {p["url"] for p in self.proxies}
            for entry in new_entries:
                if entry["url"] not in existing_urls:
                    self.proxies.append(entry)

    # ── 健康检查 ──────────────────────────────────────────────

    def health_check(self):
        """验证池中所有代理，剔除不可用的"""
        with self._lock:
            snapshot = list(self.proxies)

        results = {}
        for entry in snapshot:
            results[entry["url"]] = self._check_proxy(entry["url"])

        with self._lock:
            for entry in list(self.proxies):
                if not results.get(entry["url"], False):
                    self.proxies.remove(entry)

    def _check_proxy(self, proxy_url):
        """用 httpbin.org 验证单个代理是否可用"""
        proxies = {"http": proxy_url, "https": proxy_url}
        try:
            resp = requests.get(
                "https://httpbin.org/ip",
                proxies=proxies,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ── 内部辅助 ──────────────────────────────────────────────

    def _find_entry(self, proxy_url):
        """在 proxies 列表中查找指定 url 的条目"""
        for entry in self.proxies:
            if entry["url"] == proxy_url:
                return entry
        return None

    @staticmethod
    def _parse_proxy_item(item):
        """将各种 API 格式统一为 http://ip:port 形式的 url"""
        # 字符串格式: "ip:port" 或 "http://ip:port"
        if isinstance(item, str):
            if item.startswith("http"):
                return item
            return f"http://{item}"
        # 字典格式: {"ip": ..., "port": ..., "protocol": ...}
        if isinstance(item, dict):
            ip = item.get("ip") or item.get("host")
            port = item.get("port")
            if not ip or not port:
                return None
            protocol = item.get("protocol", "http").lower()
            return f"{protocol}://{ip}:{port}"
        return None
