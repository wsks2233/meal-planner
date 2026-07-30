"""价格读取与单位归一（共享给推荐引擎 / 进销存 / 价格接口）。

设计要点：
- latest_price_map(db)：用一次分组查询取「每个食材的最新价」，同一
  (ingredient_id, date) 存在多条（如 mock 与真实同日）时优先非模拟源，
  消除 recommender / confirm_plan 里「每食材一次查询」的 N+1。
- price_per_g(price, spec)：把任意计价规格折算成「元/克」，供成本估算统一口径。
  数据口径：本项目食材单位均为 g/ml（液体按 1ml≈1g 近似），价格常见规格为
  「元/500克」「元/kg」「元/斤」「参考价(电商)」等。
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models

MOCK_SOURCE = "模拟数据(演示)"

# 无价格记录时的兜底单价（base_price 即「元/500g」，折算为元/克）
DEFAULT_PER_G = 5.0 / 500.0


def price_per_g(price: float | None, spec: str | None) -> float:
    """把 (价格, 规格) 归一为「元/克」。无法识别规格时按元/500g 兜底。

    支持：元/500克、500g、元/kg、元/千克、元/公斤、元/斤(=500g)、元/克、元/g、
    以及无规格的电商参考价（按元/500g 近似）。
    """
    if price is None:
        return 0.0
    s = (spec or "").lower().replace(" ", "")
    if "kg" in s or "千克" in s or "公斤" in s:
        return price / 1000.0
    if "元/克" in s or "元/g" in s:
        return float(price)
    # 元/500克、500g、元/斤(=500g)、电商参考价等 → 按每 500g
    return price / 500.0


def latest_price_map(db: Session) -> dict[int, "models.PriceRecord"]:
    """单查询返回 {ingredient_id: 最新 PriceRecord}。

    用 MAX(date) 分组 + 回连取整行；同一食材同日存在多条（mock 与真实）时，
    优先保留非模拟源，保证真实价不被旧 mock 遮住。
    """
    sub = (select(models.PriceRecord.ingredient_id.label("iid"),
                  func.max(models.PriceRecord.date).label("mx"))
           .group_by(models.PriceRecord.ingredient_id).subquery())
    rows = db.scalars(
        select(models.PriceRecord)
        .join(sub, (models.PriceRecord.ingredient_id == sub.c.iid)
                   & (models.PriceRecord.date == sub.c.mx))).all()
    best: dict[int, models.PriceRecord] = {}
    for r in rows:
        cur = best.get(r.ingredient_id)
        if cur is None or (cur.source == MOCK_SOURCE and r.source != MOCK_SOURCE):
            best[r.ingredient_id] = r
    return best
