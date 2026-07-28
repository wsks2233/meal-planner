"""长期（1-2个月）采购分批规划。

思路：
1. 长期计划按"周"分段调用推荐引擎，传入上一周主菜集合施加轮换约束
   （每周主菜与上周重复率 <= 30%，即轮换 >= 70%）。
2. 汇总全周期食材缺口后，按保质期分批：
   批次数 = ceil(总天数 / min(食材保质期, 采购周期上限14天))
   每批购买量 = 总需量 / 批次数（向上取整到 50g）
   第 i 批建议购买日 = 开始日 + i * 间隔（间隔=总天数/批次数）
3. 产出"采购日历"：按建议购买日分组，可导出 ICS 加入手机系统日历。
"""
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

PURCHASE_CYCLE_CAP = 14  # 单次采购最长覆盖天数（生鲜类以保质期为准）


def batch_shopping_plan(db: Session, plan: models.MealPlan, people: int) -> list[dict]:
    """比对库存 → 缺量 → 按保质期分批。返回采购项列表（含批次与建议日期）。"""
    # 1) 汇总总需量
    need: dict[int, float] = defaultdict(float)
    for pm in plan.meals:
        recipe = db.get(models.Recipe, pm.recipe_id)
        for it in recipe.items:
            need[it.ingredient_id] += it.amount * pm.servings

    # 2) 扣除现有库存
    for ing_id in list(need):
        stock = db.scalar(
            select(models.InventoryBatch.remaining_qty)
            .where(models.InventoryBatch.ingredient_id == ing_id,
                   models.InventoryBatch.discarded == False,  # noqa: E712
                   models.InventoryBatch.expire_date >= date.today())) or 0
        need[ing_id] = max(0, need[ing_id] - stock)

    # 3) 分批
    items = []
    for ing_id, total in need.items():
        if total <= 0:
            continue
        ing = db.get(models.Ingredient, ing_id)
        latest = db.scalars(
            select(models.PriceRecord)
            .where(models.PriceRecord.ingredient_id == ing_id)
            .order_by(models.PriceRecord.date.desc()).limit(1)).first()
        price = latest.price if latest else ing.base_price
        cover = min(ing.default_shelf_life_days, PURCHASE_CYCLE_CAP)
        n_batches = max(1, math.ceil(plan.days / cover))
        per_qty = math.ceil(total / n_batches / 50) * 50  # 取整到 50g
        interval = plan.days / n_batches
        for b in range(n_batches):
            items.append({
                "ingredient_id": ing_id,
                "need_qty": per_qty,
                "unit": ing.unit,
                "est_price": round(per_qty / 500 * price, 2),
                "batch_no": b + 1,
                "suggest_date": plan.start_date + timedelta(days=round(b * interval)),
                "storage_method": ing.storage_method,
            })
    items.sort(key=lambda x: (x["suggest_date"], x["ingredient_id"]))
    return items


def build_ics(items: list[dict], db: Session) -> str:
    """生成采购日历 ICS 文件内容，手机端可导入系统日历。"""
    by_date: dict[date, list[str]] = defaultdict(list)
    for it in items:
        ing = db.get(models.Ingredient, it["ingredient_id"])
        by_date[it["suggest_date"]].append(
            f"{ing.name} {it['need_qty']:.0f}{it['unit']}")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//meal-planner//purchase-calendar//CN"]
    for d, names in sorted(by_date.items()):
        ds = d.strftime("%Y%m%d")
        lines += [
            "BEGIN:VEVENT",
            f"UID:purchase-{ds}@meal-planner",
            f"DTSTART;VALUE=DATE:{ds}",
            f"SUMMARY:🛒 采购日（{len(names)}项）",
            f"DESCRIPTION:{'、'.join(names)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
