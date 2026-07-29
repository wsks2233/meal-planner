"""菜价数据源引擎。

设计说明（数据来源合规）：
- 生产环境应优先接入公开免费 API（如各地发改委价格监测、农业农村部
  批发价格系统 http://zdscxx.moa.gov.cn），抓取时必须遵守目标站点
  robots.txt、控制频率（本项目调度器默认每日 1 次）、带缓存与重试。
- 演示环境使用 MockPriceSource 生成真实感模拟数据，前端界面明确标注
  "模拟数据(演示)"来源，不冒充真实行情。
- 新增真实数据源时只需继承 PriceSourceAdapter 并实现 fetch()。
"""
import logging
import math
import random
import time
from abc import ABC, abstractmethod
from datetime import date
from functools import wraps

log = logging.getLogger("price_engine")


def retry(times: int = 3, delay: float = 1.0):
    """简单重试装饰器：真实 API 抓取失败时按次数退避重试。"""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last = None
            for i in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    last = e
                    time.sleep(delay * (i + 1))
            raise last
        return wrapper
    return deco


class PriceSourceAdapter(ABC):
    """数据源适配器基类。真实实现示例：

    class MoaPriceSource(PriceSourceAdapter):
        source_name = "农业农村部批发价"
        @retry(times=3)
        def fetch(self, ingredients, day):
            resp = httpx.post(API_URL, json={...}, timeout=10)
            ...  # 解析并返回 {ingredient_id: price}
    """
    source_name: str = "unknown"
    _cache: dict = {}

    @abstractmethod
    def fetch(self, ingredients: list, day: date) -> dict[int, float]:
        """返回 {ingredient_id: 当日价格}。"""

    def fetch_cached(self, ingredients: list, day: date) -> dict[int, float]:
        key = (self.source_name, day.isoformat())
        if key not in self._cache:
            self._cache[key] = self.fetch(ingredients, day)
        return self._cache[key]


class MockPriceSource(PriceSourceAdapter):
    """真实感模拟价格：基准价 x 季节因子 x 周内因子 x 确定性随机扰动。

    - 季节因子：正弦波动 ±15%（冬季蔬菜贵、夏季便宜等的粗略近似）
    - 周内因子：周末略涨 3%
    - 随机扰动：以 (ingredient_id, date) 为种子的 ±8%，保证同一天查询结果稳定
    """
    source_name = "模拟数据(演示)"

    def price_for(self, base_price: float, ingredient_id: int, day: date) -> float:
        doy = day.timetuple().tm_yday
        season = 1 + 0.15 * math.sin(2 * math.pi * (doy - 30) / 365 + ingredient_id % 7)
        weekend = 1.03 if day.weekday() >= 5 else 1.0
        rng = random.Random(f"{ingredient_id}-{day.isoformat()}")
        noise = 1 + rng.uniform(-0.08, 0.08)
        return round(max(0.3, base_price * season * weekend * noise), 2)

    def fetch(self, ingredients: list, day: date) -> dict[int, float]:
        return {i.id: self.price_for(i.base_price, i.id, day) for i in ingredients}


class CompositePriceSource(PriceSourceAdapter):
    """多源降级聚合：按优先级串联多个 PriceSourceAdapter。

    - 每个食材取「第一个返回非空价」的源；记录 last_sources / last_specs 供写库标注。
    - 不在链中放入 Mock：既匹配不到政府价、也匹配不到电商价的食材，视为
      「暂无可靠价」，由上层灰标处理，绝不用模拟价冒充真实行情（合规要求）。
    - 任一源异常（网络/反爬/超时）自动跳过并降级到下一源，不阻断主流程。
    """

    source_name = "复合价格源"

    def __init__(self, sources: list):
        self.sources = sources
        self.last_sources: dict[int, str] = {}
        self.last_specs: dict[int, str] = {}

    @staticmethod
    def _spec_for(source_name: str) -> str:
        return "元/500克" if source_name == "政府指导价" else "参考价(电商)"

    def fetch(self, ingredients: list, day: date) -> dict[int, float]:
        result: dict[int, float] = {}
        self.last_sources = {}
        self.last_specs = {}
        remaining = list(ingredients)
        for src in self.sources:
            if not remaining:
                break
            try:
                prices = src.fetch(remaining, day) or {}
            except Exception as e:  # noqa: BLE001
                log.warning("%s 抓取失败，降级下一源: %s", getattr(src, "source_name", src), e)
                continue
            for iid, price in prices.items():
                if price is not None and iid not in result:
                    result[iid] = price
                    self.last_sources[iid] = src.source_name
                    self.last_specs[iid] = self._spec_for(src.source_name)
            remaining = [ing for ing in remaining if ing.id not in result]
        return result


def get_price_source() -> PriceSourceAdapter:
    """工厂：默认复合源（政府真实价 ∪ 电商平台兜底）。

    任一源初始化失败均自动跳过（政府价与电商互不影响），全部失败才退回 Mock，
    保证系统始终有价可用、且优先使用真实数据。
    """
    sources: list = []
    try:
        from .gov_price_source import GovPriceSource
        sources.append(GovPriceSource())
    except Exception as e:  # noqa: BLE001
        log.warning("政府价源初始化失败: %s", e)
    try:
        from .ecommerce_source import EcommercePriceSource
        sources.append(EcommercePriceSource())
    except Exception as e:  # noqa: BLE001
        log.warning("电商价格源初始化失败，跳过: %s", e)
    if not sources:
        log.warning("无可用真实价格源，退回 MockPriceSource")
        return MockPriceSource()
    return CompositePriceSource(sources)
