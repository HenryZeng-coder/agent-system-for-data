"""Scrapy 下载中间件 — 代理轮换 / UA随机化 / 429/5xx自动重试

注意: utils 目录位于 crawler/ 下而非 wuhan_it_crawler/ 包内，
因此采用延迟导入避免 Scrapy 加载中间件时 ModuleNotFoundError。
"""

import time
import logging

from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


def _import_utils():
    """延迟导入 utils 模块 (位于 crawler/utils/ 下，不在 wuhan_it_crawler 包内)"""
    import sys
    import os
    utils_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from proxy_pool import ProxyPool
    from ua_rotator import UARotator
    from anti_detect import AntiDetect
    return ProxyPool, UARotator, AntiDetect


class ProxyMiddleware:
    """代理IP中间件 — 从 ProxyPool 获取代理并注入请求"""

    def __init__(self, proxy_pool=None):
        if proxy_pool is not None:
            self.proxy_pool = proxy_pool
        else:
            ProxyPool, _, _ = _import_utils()
            self.proxy_pool = ProxyPool()

    def process_request(self, request, spider):
        proxy = self.proxy_pool.get_proxy()
        if proxy:
            request.meta["proxy"] = proxy
            logger.debug("Using proxy: %s", proxy)

    def process_exception(self, request, exception, spider):
        proxy = request.meta.get("proxy")
        if proxy:
            self.proxy_pool.mark_failed(proxy)
            logger.warning("Proxy %s failed with %s, marked as failed", proxy, exception)


class UARotateMiddleware:
    """User-Agent 随机轮换中间件 — 使用 UARotator + AntiDetect 随机头"""

    def __init__(self, ua_rotator=None, anti_detect=None):
        if ua_rotator is not None or anti_detect is not None:
            self.ua_rotator = ua_rotator or UARotator()
            self.anti_detect = anti_detect or AntiDetect(ua_rotator=self.ua_rotator)
        else:
            _, UARotator, AntiDetect = _import_utils()
            self.ua_rotator = UARotator()
            self.anti_detect = AntiDetect(ua_rotator=self.ua_rotator)

    def process_request(self, request, spider):
        headers = self.anti_detect.generate_headers()
        for key, value in headers.items():
            request.headers[key] = value


class RetryMiddleware:
    """429 / 5xx 自动重试中间件 — 配合 AntiDetect 自适应延迟"""

    RETRY_5XX_STATUS_CODES = [500, 502, 503, 504]

    def __init__(self, anti_detect=None):
        if anti_detect is not None:
            self.anti_detect = anti_detect
        else:
            _, _, AntiDetect = _import_utils()
            self.anti_detect = AntiDetect()

    def process_request(self, request, spider):
        request.meta["_anti_detect_delay"] = self.anti_detect.get_delay()

    def process_response(self, request, response, spider):
        status = response.status

        if status == 200:
            self.anti_detect.on_success()
            return response

        if status == 429:
            self.anti_detect.on_429()
            delay = self.anti_detect.get_delay()
            logger.warning(
                "429 rate-limited on %s, backing off %.1fs before retry",
                request.url, delay,
            )
            time.sleep(delay)
            retry_req = request.copy()
            retry_req.meta["retry_times"] = retry_req.meta.get("retry_times", 0) + 1
            retry_req.dont_filter = True
            return retry_req

        if status in self.RETRY_5XX_STATUS_CODES:
            can_retry = self.anti_detect.on_5xx()
            if can_retry:
                delay = self.anti_detect.get_delay()
                logger.warning(
                    "5xx (%d) on %s, retrying in %.1fs (attempt %d/%d)",
                    status, request.url, delay,
                    self.anti_detect._5xx_retry_count,
                    self.anti_detect._5xx_max_retries,
                )
                time.sleep(delay)
                retry_req = request.copy()
                retry_req.meta["retry_times"] = retry_req.meta.get("retry_times", 0) + 1
                retry_req.dont_filter = True
                return retry_req
            else:
                logger.error(
                    "5xx (%d) on %s exceeded max retries (%d), giving up",
                    status, request.url, self.anti_detect._5xx_max_retries,
                )
                return response

        return response

    def process_exception(self, request, exception, spider):
        """连接异常时也尝试重试"""
        can_retry = self.anti_detect.on_5xx()
        if can_retry:
            delay = self.anti_detect.get_delay()
            logger.warning(
                "Exception on %s (%s), retrying in %.1fs",
                request.url, exception, delay,
            )
            time.sleep(delay)
            retry_req = request.copy()
            retry_req.meta["retry_times"] = retry_req.meta.get("retry_times", 0) + 1
            retry_req.dont_filter = True
            return retry_req
        return None
