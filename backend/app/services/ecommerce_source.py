"""电商价格兜底源（Playwright 无头浏览器抓取）。

仅在政府价匹配不到时使用。机制（用户已确认）：
- 优先用「慢慢买」比价网（s.manmanbuy.com，无登录墙、价格直出）；
- 京东 / 淘宝作兜底（多数会被登录墙反爬挡住，命中即降级）；
- 命中验证码 / 登录墙 / 限流页立即 abort 返回 None，由上层灰标「暂无可靠价」；
- **请求频率硬约束**（用户特别强调）：两次抓取最小间隔 3s + 随机抖动、
  每日预算上限、每食材 24h 缓存、单飞串行——避免被目标站限流/封 IP；
- 合规：个人非商业用途，已用户确认接受爬取风险。

解析逻辑用 bs4（可离线单测）；抓取编排用 Playwright。
注意：慢慢买为聚合「促销/历史价」，多为整包价，单位可能与 500g 不同，
仅作电商参考价兜底，不保证与政府价单位一致。
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .price_engine import PriceSourceAdapter, retry

log = logging.getLogger("ecommerce_source")

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "ecommerce_cache.json"
CACHE_TTL_HOURS = 24
MIN_INTERVAL_S = 3.0       # 两次抓取最小间隔（拟人 + 防封，用户要求控制频率）
JITTER_S = (0.5, 2.0)      # 额外随机抖动区间，进一步打散请求节奏
DAILY_BUDGET = 100         # 每日最多抓取次数（硬上限，个人使用足够）
CAPTCHA_HINTS = ["验证码", "安全验证", "请完成安全", "确认您不是机器人", "登录后查看", "slide to verify"]
RATE_LIMIT_HINTS = ["访问出错了", "访问过于频繁", "请求频率过快", "稍后再试"]

_lock = threading.Lock()
_daily_count = 0
_last_fetch_ts = 0.0


def _now() -> float:
    return time.time()


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(c: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def _cached_price(name: str) -> float | None:
    item = _load_cache().get(name)
    if item and (datetime.now() - datetime.fromisoformat(item["ts"])).total_seconds() < CACHE_TTL_HOURS * 3600:
        return float(item["price"])
    return None


def _store_price(name: str, price: float) -> None:
    c = _load_cache()
    c[name] = {"price": price, "ts": datetime.now().isoformat()}
    _save_cache(c)


def _is_captcha(text: str) -> bool:
    low = (text or "").lower()
    return any(h.lower() in low for h in CAPTCHA_HINTS)


def _to_float(s) -> float | None:
    s = (s or "").strip()
    if s in ("", "-", "—", "暂无", "无"):
        return None
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def extract_jd_price(html: str) -> float | None:
    """从京东搜索结果页 HTML 提取首个合理价格（离线可测）。"""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("[data-price]"):
        v = _to_float(el.get("data-price"))
        if v and 0.1 < v < 100000:
            return v
    for el in soup.select(".p-price i, .p-price strong"):
        v = _to_float(el.get_text())
        if v and 0.1 < v < 100000:
            return v
    return None


def extract_taobao_price(html: str) -> float | None:
    """从淘宝搜索结果页 HTML 提取首个合理价格（离线可测）。"""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("[data-price], .price .c-price, .price-now, [class*=price]"):
        v = _to_float(el.get("data-price") or el.get_text())
        if v and 0.1 < v < 100000:
            return v
    return None


def _price_in_text(text: str) -> float | None:
    """从一段文本里提取首个「数字+元」价格（如 '42元' / '3.5 元'）。"""
    if not text:
        return None
    m = re.search(r"(\d{1,4}(?:\.\d+)?)\s*元", text)
    if m:
        v = float(m.group(1))
        if 0.1 < v < 100000:
            return v
    return None


def extract_manmanbuy_price(html: str) -> float | None:
    """从慢慢买搜索结果页提取首个商品参考价（离线可测）。

    价格 DOM 形如：
      <div class="DiscountItemPC_itemSubTitle__rWgWK"><a ...>42元</a></div>
    CSS 类带 hash 后缀，但含稳定子串 'itemSubTitle'，优先取它；
    兜底取全文首个「数字+元」。
    """
    soup = BeautifulSoup(html, "html.parser")
    for div in soup.find_all("div", class_=re.compile("itemSubTitle")):
        a = div.find("a")
        if a:
            v = _price_in_text(a.get_text())
            if v:
                return v
    # 兜底：全文首个合理价
    return _price_in_text(soup.get_text())


class EcommercePriceSource(PriceSourceAdapter):
    """电商兜底价格源：政府价匹配不到的食材在此取价。"""

    source_name = "电商平台参考价"

    def __init__(self, headless: bool = True):
        self.headless = headless

    @retry(times=2, delay=1.5)
    def _quote(self, browser, name: str, site: str) -> float | None:
        from urllib.parse import quote
        kw = quote(name)
        url = (
            f"https://search.jd.com/Search?keyword={kw}"
            if site == "jd"
            else f"https://s.taobao.com/search?q={kw}"
        )
        page = browser.new_page()
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            # 登录墙快速识别：主流电商对无头流量常重定向到 passport/login，
            # 此时商品网格不渲染，直接降级，避免无谓等待。
            if any(k in page.url for k in ("passport", "login.taobao", "login.tmall",
                                           "sec.taobao", "verify", "risk")):
                log.warning("[%s] %s 被重定向到登录/风控页(%s)，跳过", site, name, page.url)
                return None
            page.wait_for_timeout(1800)  # 等 JS 渲染价格
            txt = page.inner_text("body") or ""
            if _is_captcha(txt):
                log.warning("[%s] %s 命中验证码/登录墙，跳过", site, name)
                return None
            html = page.content()
            price = extract_jd_price(html) if site == "jd" else extract_taobao_price(html)
            return price
        finally:
            page.close()

    @retry(times=2, delay=2.0)
    def _quote_manmanbuy(self, browser, name: str) -> float | None:
        """慢慢买（s.manmanbuy.com）搜索取价，无登录墙、价格直出。"""
        from urllib.parse import quote
        url = (
            "https://s.manmanbuy.com/pc/search/result?keyword="
            + quote(name)
            + "&btnSearch="
            + quote("搜索")
        )
        page = browser.new_page()
        try:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            # 限流/出错页：title 含「访问出错了」，或 URL 落到 error
            if any(k in page.url for k in ("passport", "login", "verify", "risk", "error")):
                log.warning("manmanbuy %s 落到异常页(%s)，跳过", name, page.url)
                return None
            page.wait_for_timeout(2500)  # 等 JS 渲染
            txt = page.inner_text("body") or ""
            if _is_captcha(txt) or any(h in txt for h in RATE_LIMIT_HINTS):
                log.warning("manmanbuy %s 命中反爬/限流页，跳过", name)
                return None
            return extract_manmanbuy_price(page.content())
        finally:
            page.close()

    def _launch_kwargs(self) -> dict:
        """代理策略（部署可控）：
        - 设 ECOMMERCE_PROXY=URL  → 走该代理（需能访问目标站）；
        - 设 ECOMMERCE_PROXY=direct → 清掉代理环境变量，强制直连（本沙箱走这条）；
        - 不设 → 沿用系统默认。"""
        proxy = os.environ.get("ECOMMERCE_PROXY")
        if proxy and proxy.lower() != "direct":
            return {"proxy": {"server": proxy}}
        if proxy and proxy.lower() == "direct":
            clean = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
            return {"env": clean}
        return {}

    def fetch(self, ingredients: list, day: date) -> dict[int, float]:
        """返回 {ingredient_id: 电商参考价}；取不到的食材不出现（上层灰标）。

        取价顺序：慢慢买(主) → 京东 → 淘宝(兜底)。每次抓取都过 _rate_limit 限流。
        """
        result: dict[int, float] = {}
        pending = []
        for ing in ingredients:
            cp = _cached_price(ing.name)
            if cp is not None:
                result[ing.id] = cp
            else:
                pending.append(ing)
        if not pending:
            return result

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                **self._launch_kwargs(),
            )
            try:
                for ing in pending:
                    if not self._rate_limit():
                        log.warning("达每日预算上限，其余食材转灰标")
                        break
                    price = None
                    # 主源：慢慢买；兜底：京东/淘宝
                    for getter in (self._quote_manmanbuy,
                                   lambda b, n: self._quote(b, n, "jd"),
                                   lambda b, n: self._quote(b, n, "taobao")):
                        try:
                            price = getter(browser, ing.name)
                        except Exception as e:  # noqa: BLE001
                            log.warning("%s 抓取异常: %s", ing.name, e)
                            price = None
                        if price is not None:
                            break
                    if price is not None:
                        _store_price(ing.name, price)
                        result[ing.id] = price
            finally:
                browser.close()
        return result

    @staticmethod
    def _rate_limit() -> bool:
        """预算内返回 True 并执行限流（含随机抖动）；否则 False。

        严格串行 + 最小间隔 + 抖动，避免被目标站按固定频率识别/限流。
        """
        global _daily_count, _last_fetch_ts
        with _lock:
            if _daily_count >= DAILY_BUDGET:
                return False
            elapsed = _now() - _last_fetch_ts
            wait = MIN_INTERVAL_S - elapsed + random.uniform(*JITTER_S)
            if wait > 0:
                time.sleep(wait)
            _last_fetch_ts = _now()
            _daily_count += 1
            return True
