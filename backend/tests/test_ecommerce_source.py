"""电商价格源离线单测（不依赖外网/浏览器）。

覆盖：价格解析、验证码检测、缓存 TTL、限流预算、整体 fetch 编排（mock 抓取）。
"""
import sys, types, datetime
sys.path.insert(0, ".")

from app.services import ecommerce_source as es
from app.services.pricing import parse_weight_g


class _FakeIngredient:
    def __init__(self, id, name, base_price=5.0):
        self.id = id
        self.name = name
        self.base_price = base_price


# ---- 1) 京东价格解析 ----
JD_HTML = """
<html><body>
  <div class="gl-item"><div class="p-price"><i data-price="12.80">12.80</i></div></div>
  <div class="gl-item"><div class="p-price"><strong>9.90</strong></div></div>
</body></html>
"""
assert es.extract_jd_price(JD_HTML) == 12.80, "应取首个 data-price"


# ---- 2) 淘宝价格解析 ----
TB_HTML = """
<html><body>
  <div class="item"><span class="price"><em class="c-price">¥15.50</em></span></div>
</body></html>
"""
assert es.extract_taobao_price(TB_HTML) == 15.50, "应取首个合理价"


# ---- 2b) 慢慢买价格解析 ----
MMB_HTML = """
<html><body>
  <div class="nav"><a>导航 9.9元包邮</a></div>
  <div class="DiscountItemPC_itemSubTitle__rWgWK"><a target="_blank" href="https://cu.manmanbuy.com/discuxiao_1.aspx">42元</a></div>
  <div class="DiscountItemPC_itemSubTitle__abcd"><a href="x">3.5元</a></div>
</body></html>
"""
assert es.extract_manmanbuy_price(MMB_HTML) == 42.0, "应优先取商品卡片价(42元)"
# 无 itemSubTitle 时兜底取全文首个 数字+元
assert es.extract_manmanbuy_price("<p>今日特价 12.8 元 限时</p>") == 12.8
assert es.extract_manmanbuy_price("<p>无价格文本</p>") is None


# ---- 3) 验证码检测 ----
assert es._is_captcha("请完成安全验证后再访问") is True
assert es._is_captcha("普通商品价格列表 12.5 元") is False


# ---- 4) 缓存写入/读取（TTL 内命中）----
es._store_price("测试葱", 3.3)
assert es._cached_price("测试葱") == 3.3
# 过期项不命中
import json
from pathlib import Path
old = {"测试葱旧": {"price": 1.0, "ts": (datetime.datetime.now() - datetime.timedelta(hours=25)).isoformat()}}
Path(es.CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(es.CACHE_PATH).write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
assert es._cached_price("测试葱旧") is None, "超 24h 应视为未命中"


# ---- 5) 限流预算 ----
es._daily_count = 0
assert es.EcommercePriceSource._rate_limit() is True
es._daily_count = es.DAILY_BUDGET
assert es.EcommercePriceSource._rate_limit() is False
es._daily_count = 0


# ---- 6) 整体 fetch 编排（mock 浏览器与 _quote，纯离线）----
class _FakePage:
    url = "https://s.manmanbuy.com/pc/search/result?keyword=x"
    def goto(self, *a, **k): pass
    def wait_for_timeout(self, *a, **k): pass
    def inner_text(self, *a, **k): return "普通商品价格"
    def content(self): return "<html></html>"
    def close(self): pass

class _FakeBrowser:
    def new_page(self): return _FakePage()
    def close(self): pass

class _FakePW:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    @property
    def chromium(self):
        class C:
            def launch(self, *a, **k): return _FakeBrowser()
        return C()

# 打桩浏览器启动，使其不依赖 chromium 二进制
_orig_pw = es.sync_playwright
es.sync_playwright = lambda: _FakePW()

src = es.EcommercePriceSource()
ings = [_FakeIngredient(1, "鸡腿"), _FakeIngredient(2, "猪肉馅"), _FakeIngredient(3, "大葱")]

def fake_quote(self, browser, name, site):
    return {"鸡腿": 11.2, "猪肉馅": 18.5, "大葱": 4.0}.get(name)

import types as _t
src._quote = _t.MethodType(fake_quote, src)

# 清缓存避免命中缓存绕过 mock
Path(es.CACHE_PATH).write_text("{}", encoding="utf-8")
res = src.fetch(ings, datetime.date.today())
assert res == {1: 11.2, 2: 18.5, 3: 4.0}, f"fetch 应返回 mock 价, got {res}"
# 再次 fetch 应命中缓存（不再调用 _quote，且值一致）
res2 = src.fetch(ings, datetime.date.today())
assert res2 == res

es.sync_playwright = _orig_pw  # 还原

# ---- 克重解析 ----
assert parse_weight_g("金龙鱼大米 5kg") == 5000.0
assert parse_weight_g("东北珍珠米 10公斤装") == 10000.0
assert parse_weight_g("特级 大米 2.5kg") == 2500.0
assert parse_weight_g("面粉 500g") == 500.0
assert parse_weight_g("小米 500g*2袋") == 500.0  # 取首个数字+克
assert parse_weight_g("新鲜土鸡蛋 30枚") is None
assert parse_weight_g("金龙鱼花生油 5L") is None  # L ≠ 重量
assert parse_weight_g("散装 大葱 1斤") == 500.0
assert parse_weight_g("") is None
print("[OK] parse_weight_g 克重解析")

print("ALL ECOMMERCE OFFLINE TESTS PASSED ✅")
