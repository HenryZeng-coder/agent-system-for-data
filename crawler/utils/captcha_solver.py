"""验证码识别"""

import asyncio
import logging
import random
import time

logger = logging.getLogger(__name__)


class CaptchaSolver:
    """验证码处理: 图片(ddddocr)/滑块(Playwright)/点选(频率控制)"""

    def __init__(self, ocr=None, slider_selector='div.slider-btn, div.slider_button, '
                 'div.btn_slide, span.slider-btn, div.slide-block',
                 bg_selector='div.slider_bg, div.cut_bg, div.captcha-bg-img'):
        """
        初始化验证码求解器。

        Args:
            ocr: ddddocr 实例，若为 None 则延迟创建。
            slider_selector: 滑块按钮的 CSS 选择器（支持逗号分隔多个候选）。
            bg_selector: 滑块背景图的 CSS 选择器（支持逗号分隔多个候选）。
        """
        self._ocr = ocr
        self.slider_selector = slider_selector
        self.bg_selector = bg_selector
        self._last_click_attempt = 0.0
        self._click_min_interval = 30.0  # 点选验证码两次尝试之间的最短间隔(秒)

    # ------------------------------------------------------------------
    # ddddocr 延迟初始化
    # ------------------------------------------------------------------

    @property
    def ocr(self):
        """延迟加载 ddddocr，避免模块导入时就触发较重的模型加载。"""
        if self._ocr is None:
            try:
                import ddddocr
                self._ocr = ddddocr.DdddOcr(show_ad=False)
                logger.info("ddddocr 实例创建成功")
            except ImportError:
                logger.error("ddddocr 未安装，请执行 pip install ddddocr")
                raise
            except Exception as exc:
                logger.error("ddddocr 初始化失败: %s", exc)
                raise
        return self._ocr

    # ------------------------------------------------------------------
    # 图片验证码
    # ------------------------------------------------------------------

    def solve_image(self, image_bytes):
        """
        图片验证码识别（英数字混合验证码）。

        Args:
            image_bytes: 验证码图片的二进制数据（bytes）。

        Returns:
            str: 识别出的验证码文本；识别失败时返回空字符串。

        Raises:
            ValueError: image_bytes 为空或类型不正确。
        """
        if not image_bytes:
            raise ValueError("image_bytes 不能为空")
        if not isinstance(image_bytes, bytes):
            raise ValueError("image_bytes 必须是 bytes 类型，收到 %s", type(image_bytes).__name__)

        try:
            result = self.ocr.classification(image_bytes)
            logger.info("图片验证码识别结果: %s", result)
            return result or ""
        except Exception as exc:
            logger.error("图片验证码识别异常: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # 滑块验证码
    # ------------------------------------------------------------------

    def solve_slider(self, page, max_retries=3, offset_ratio=0.85):
        """
        滑块验证码：定位滑块元素、计算偏移量、模拟鼠标拖动。

        通过 Playwright Page 对象操作，支持异步与同步调用场景。
        若 page 在 asyncio 事件循环中运行，将自动使用 await。

        Args:
            page: Playwright 的 Page 对象。
            max_retries: 最大重试次数，默认 3。
            offset_ratio: 实际拖动距离占背景缺口宽度的比例（人类不会精确拖到底），
                          默认 0.85。

        Returns:
            bool: 滑块是否成功滑动。注意：仅表示拖动动作完成，不代表验证通过。
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("滑块验证码尝试 %d/%d", attempt, max_retries)
                slider_el = self._locate_slider(page)
                if slider_el is None:
                    logger.warning("未找到滑块元素，选择器: %s", self.slider_selector)
                    continue

                offset = self._calc_offset(page, offset_ratio)
                if offset <= 0:
                    logger.warning("计算的偏移量无效 (%.1f)，尝试使用默认值", offset)
                    offset = 200  # 兜底默认偏移

                self._drag_slider(page, slider_el, offset)
                logger.info("滑块拖动完成，偏移量: %.1f", offset)
                return True

            except Exception as exc:
                logger.error("滑块验证码第 %d 次尝试失败: %s", attempt, exc)
                # 短暂等待后重试
                time.sleep(random.uniform(0.5, 1.5))

        logger.error("滑块验证码在 %d 次尝试后仍然失败", max_retries)
        return False

    # ---- 滑块辅助方法 ----

    def _locate_slider(self, page):
        """在页面上定位滑块按钮元素，返回第一个匹配的 ElementHandle 或 None。"""
        selectors = [s.strip() for s in self.slider_selector.split(",")]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el is not None:
                    logger.debug("通过选择器 '%s' 定位到滑块元素", sel)
                    return el
            except Exception:
                continue
        return None

    def _calc_offset(self, page, offset_ratio):
        """
        计算滑块需要拖动的偏移量。

        优先尝试从背景图元素的宽度推断缺口位置；若无法获取则回退到固定值。

        Args:
            page: Playwright Page。
            offset_ratio: 偏移比例。

        Returns:
            float: 偏移像素数。
        """
        # 尝试从背景图元素获取缺口位置
        selectors = [s.strip() for s in self.bg_selector.split(",")]
        for sel in selectors:
            try:
                bg_el = page.query_selector(sel)
                if bg_el is not None:
                    box = bg_el.bounding_box()
                    if box and box.get("width"):
                        offset = box["width"] * offset_ratio
                        logger.debug("从背景元素 '%s' 计算偏移: %.1f", sel, offset)
                        return offset
            except Exception:
                continue

        # 回退: 从滑块容器推断
        try:
            container = page.query_selector("div.slider, div.captcha-slider, div.slide-verify")
            if container is not None:
                box = container.bounding_box()
                if box and box.get("width"):
                    offset = box["width"] * offset_ratio
                    logger.debug("从容器元素计算偏移: %.1f", offset)
                    return offset
        except Exception:
            pass

        logger.warning("无法从页面元素计算偏移量，将使用默认值")
        return 0

    def _drag_slider(self, page, slider_el, offset):
        """
        模拟人类拖动滑块：先加速后减速，带随机抖动。

        Args:
            page: Playwright Page。
            slider_el: 滑块元素 ElementHandle。
            offset: 需要拖动的总像素距离。
        """
        box = slider_el.bounding_box()
        if not box:
            raise RuntimeError("无法获取滑块元素的 bounding_box")

        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2

        # 将拖动分为多步，模拟人类先快后慢的轨迹
        steps = random.randint(20, 35)
        # 加速阶段占比
        accel_ratio = 0.6

        page.mouse.move(start_x, start_y)
        page.mouse.down()

        current_x = start_x
        for i in range(1, steps + 1):
            progress = i / steps
            if progress < accel_ratio:
                # 加速阶段：步长较大
                step_ratio = progress / accel_ratio
                step_size = (offset / steps) * (1.0 + step_ratio)
            else:
                # 减速阶段：步长逐渐缩小
                decel_progress = (progress - accel_ratio) / (1 - accel_ratio)
                step_size = (offset / steps) * (1.0 - 0.5 * decel_progress)

            # 添加 Y 轴轻微抖动
            jitter_y = random.uniform(-1.5, 1.5)
            current_x += step_size
            page.mouse.move(current_x, start_y + jitter_y)

            # 步间随机微延迟，更接近人类操作
            time.sleep(random.uniform(0.008, 0.025))

        # 松开鼠标前短暂停顿
        time.sleep(random.uniform(0.1, 0.3))
        page.mouse.up()

    # ------------------------------------------------------------------
    # 点选验证码
    # ------------------------------------------------------------------

    def solve_click(self, page):
        """
        点选验证码处理：降低频率并跳过。

        点选类验证码（如汉字点选、图标点选）需要语义理解与坐标映射，
        自动化难度极高且成功率低。因此采取以下策略：
          1. 频率控制：两次尝试之间至少间隔 _click_min_interval 秒。
          2. 直接跳过并记录日志，由人工介入或上层逻辑更换采集路径。

        Args:
            page: Playwright 的 Page 对象（保留参数以保持接口一致）。

        Returns:
            bool: 始终返回 False，表示未自动解决。
        """
        now = time.time()
        elapsed = now - self._last_click_attempt

        if elapsed < self._click_min_interval:
            remaining = self._click_min_interval - elapsed
            logger.warning(
                "点选验证码触发频率过高，距上次仅 %.1f 秒，"
                "建议至少等待 %.1f 秒后重试",
                elapsed, self._click_min_interval,
            )
            logger.info("当前需等待 %.1f 秒", remaining)
            return False

        self._last_click_attempt = now
        logger.warning(
            "检测到点选验证码，该类型验证码自动化成功率低，已跳过。"
            "建议人工介入或调整采集策略。"
        )
        return False
