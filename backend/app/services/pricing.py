"""价格读取与单位归一（共享给推荐引擎 / 进销存 / 价格接口）。

设计要点：
- latest_price_map(db)：用一次分组查询取「每个食材的最新价」，同一
  (ingredient_id, date) 存在多条（如 mock 与真实同日）时优先非模拟源，
  消除 recommender / confirm_plan 里「每食材一次查询」的 N+1。
- price_per_g(price, spec)：把任意计价规格折算成「元/克」，供成本估算统一口径。
  数据口径：本项目食材单位均为 g/ml（液体按 1ml≈1g 近似），价格常见规格为
  「元/500克」「元/kg」「元/斤」「参考价(电商)」等。
"""
import re
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models

MOCK_SOURCE = "模拟数据(演示)"
GOV_SOURCE = "政府指导价"
ECOM_SOURCE = "电商平台参考价"

# 无价格记录时的兜底单价（base_price 即「元/500g」，折算为元/克）
DEFAULT_PER_G = 5.0 / 500.0

# 成本/预算计算只信任这些来源（电商参考价是「整件/打包价」，单位不可靠，
# 直接进成本会把预算算爆 —— 实测慢慢买「小米=2327元」。故电商价仅展示、不进成本）。
# 但若电商源成功从商品标题解析出克重并归一化为「元/500克」，
# 规格即含明确单位 → 纳入成本。
COST_TRUSTED_SOURCES = {GOV_SOURCE}


def _spec_is_normalized(spec: str | None) -> bool:
    """规格是否含明确计价单位（元/500克 · 元/kg · 元/斤），非模糊「参考价(电商)」。"""
    s = (spec or "").lower()
    return any(u in s for u in ("500克", "500g", "/kg", "千克", "公斤", "/斤", "元/克", "元/g"))


def cost_per_g(rec: "models.PriceRecord | None", base_price: float) -> float:
    """成本估算口径单价（元/克）。

    - 政府指导价或已归一化（规格含明确单位）：可信，进成本。
    - 电商「参考价(电商)」、mock、无记录：回退 base_price 兜底。
    展示层（/latest）仍可用电商价，仅成本计算走此护栏。
    """
    if rec is not None and (rec.source in COST_TRUSTED_SOURCES
                            or _spec_is_normalized(rec.spec)):
        return price_per_g(rec.price, rec.spec)
    return (base_price or 5.0) / 500.0


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


def parse_weight_g(title: str) -> float | None:
    """从标题/规格描述中提取克重。返回克数；无法解析时返回 None。

    ⚠ 注意：「数字+枚/条/袋/包/箱/L」等非重量单位不会被解析；
       只有 kg/公斤/斤/克/g 才算。
    """
    if not title:
        return None
    t = title.lower().replace(" ", "").replace("　", "")
    # kg / 公斤 / 千克 → ×1000
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|公斤|千克)", t)
    if m:
        return float(m.group(1)) * 1000
    # 斤 → ×500
    m = re.search(r"(\d+(?:\.\d+)?)\s*斤", t)
    if m:
        return float(m.group(1)) * 500
    # 克 / g（排除 "kg" 末尾的 'g'）
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?<![k])(克|g)\b", t)
    if m:
        val = float(m.group(1))
        if 0.1 < val < 500000:
            return val
    return None
