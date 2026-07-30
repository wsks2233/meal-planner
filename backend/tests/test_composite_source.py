"""CompositePriceSource 离线单测：多源优先级合并 + 逐食材来源/规格记录。
不依赖网络/浏览器，用假源验证降级聚合逻辑。
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

from app.services.price_engine import CompositePriceSource, PriceSourceAdapter


class _FakeSrc(PriceSourceAdapter):
    def __init__(self, name, prices):
        self.source_name = name
        self._prices = prices

    def fetch(self, ingredients, day):
        # 仅返回该源"认识"的食材价
        return {i.id: p for i, p in
                ((ing, self._prices.get(ing.id)) for ing in ingredients)
                if p is not None}


class _BoomSrc(PriceSourceAdapter):
    """故意抛错的源，验证异常被跳过且不阻断。"""
    source_name = "会崩的源"

    def fetch(self, ingredients, day):
        raise RuntimeError("boom")


def _ings():
    return [type("I", (), {"id": i, "name": f"食材{i}"})() for i in (1, 2, 3, 4)]


def test_priority_wins_and_merge():
    a = _FakeSrc("政府指导价", {1: 10.0, 2: 20.0})
    b = _FakeSrc("电商平台参考价", {2: 99.0, 3: 30.0})   # 2 在 A 已有，应被 A 抢占
    c = _FakeSrc("模拟数据(演示)", {4: 40.0})            # 4 仅 C 有
    comp = CompositePriceSource([a, b, c])
    res = comp.fetch(_ings(), date.today())
    assert res == {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}, res
    # 逐食材来源
    assert comp.last_sources[1] == "政府指导价"
    assert comp.last_sources[2] == "政府指导价"   # A 优先，不是 B 的 99
    assert comp.last_sources[3] == "电商平台参考价"
    assert comp.last_sources[4] == "模拟数据(演示)"
    # 规格：政府→元/500克，其余→参考价
    assert comp.last_specs[1] == "元/500克"
    assert comp.last_specs[3] == "参考价(电商)"


def test_exception_source_skipped():
    a = _FakeSrc("政府指导价", {1: 10.0})
    boom = _BoomSrc()
    comp = CompositePriceSource([boom, a])
    res = comp.fetch(_ings(), date.today())
    assert res == {1: 10.0}, res
    assert comp.last_sources[1] == "政府指导价"


def test_unmatched_not_filled_with_mock():
    # 仅政府有 1，其它无源 → 2/3/4 不应出现在结果（交由前端灰标）
    a = _FakeSrc("政府指导价", {1: 10.0})
    comp = CompositePriceSource([a])
    res = comp.fetch(_ings(), date.today())
    assert set(res.keys()) == {1}, res


if __name__ == "__main__":
    test_priority_wins_and_merge()
    test_exception_source_skipped()
    test_unmatched_not_filled_with_mock()
    print("ALL COMPOSITE TESTS PASSED")
