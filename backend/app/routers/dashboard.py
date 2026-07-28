from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import EXPIRING_SOON_DAYS
from ..database import get_db
from .. import models

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db)):
    today = date.today()
    s = db.scalars(select(models.FamilySettings)).first()

    # 本周预算使用（最近一个覆盖今天的计划）
    plan = db.scalars(select(models.MealPlan)
                      .options(selectinload(models.MealPlan.meals))
                      .order_by(models.MealPlan.id.desc())).first()
    budget_info = None
    if plan:
        spent = sum(m.est_cost for m in plan.meals if m.date <= today)
        budget_info = {"budget": plan.budget, "total_cost": plan.total_cost,
                       "spent_so_far": round(spent, 2), "mode": plan.mode,
                       "plan_id": plan.id, "status": plan.status,
                       "usage_pct": round(plan.total_cost / plan.budget * 100, 1)
                       if plan.budget else 0}

    # 营养达标率 & 饮食依从度（近 7 天已完成餐次）
    week_ago = today - timedelta(days=6)
    meals = db.scalars(select(models.PlanMeal)
                       .where(models.PlanMeal.date >= week_ago,
                              models.PlanMeal.date <= today)).all()
    done = [m for m in meals if m.done_status == "done"]
    adherence = round(len(done) / len(meals) * 100, 1) if meals else None

    tmpl = db.scalars(select(models.NutritionTemplate)
                      .where(models.NutritionTemplate.is_active == True)).first()  # noqa: E712
    nutrition = None
    if tmpl and meals:
        actual = {"protein": 0.0, "carb": 0.0, "fat": 0.0}
        for m in meals:
            r = db.get(models.Recipe, m.recipe_id)
            actual["protein"] += r.protein_g * m.servings
            actual["carb"] += r.carb_g * m.servings
            actual["fat"] += r.fat_g * m.servings
        days_cnt = len({m.date for m in meals})
        people = s.people if s else 3
        factor = days_cnt * people if tmpl.scope == "daily" else people * days_cnt / 7
        nutrition = {k: round(actual[k] / (getattr(tmpl, f"{k}_g") * factor) * 100, 1)
                     for k in actual}

    # 临期/过期提醒（红色角标数）
    batches = db.scalars(select(models.InventoryBatch)
                         .options(selectinload(models.InventoryBatch.ingredient))
                         .where(models.InventoryBatch.discarded == False,  # noqa: E712
                                models.InventoryBatch.remaining_qty > 0)).all()
    expiring = [{"batch_id": b.id, "name": b.ingredient.name, "icon": b.ingredient.icon,
                 "remaining_qty": b.remaining_qty, "unit": b.unit,
                 "days_left": (b.expire_date - today).days,
                 "location": b.location}
                for b in batches
                if (b.expire_date - today).days <= EXPIRING_SOON_DAYS]
    expiring.sort(key=lambda x: x["days_left"])

    # 菜价小图：涨跌幅最大的 4 种常用食材近 7 天
    movers = []
    for ing in db.scalars(select(models.Ingredient).limit(40)).all():
        rows = db.scalars(select(models.PriceRecord)
                          .where(models.PriceRecord.ingredient_id == ing.id,
                                 models.PriceRecord.date >= today - timedelta(days=7))
                          .order_by(models.PriceRecord.date)).all()
        if len(rows) >= 2 and rows[0].price:
            movers.append({
                "ingredient_id": ing.id, "name": ing.name, "icon": ing.icon,
                "price": rows[-1].price,
                "change": round((rows[-1].price - rows[0].price) / rows[0].price * 100, 1),
                "spark": [r.price for r in rows]})
    movers.sort(key=lambda x: -abs(x["change"]))

    return {"budget": budget_info, "nutrition_rate": nutrition,
            "adherence": adherence, "expiring": expiring,
            "expiring_count": len(expiring), "price_movers": movers[:4],
            "shopping_pending": db.scalar(
                select(models.ShoppingItem.id)
                .where(models.ShoppingItem.bought == False).limit(1)) is not None}  # noqa: E712
