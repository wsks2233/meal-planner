"""confirm_plan 扣减与单位归一的集成测试。

用「元/千克」价格验证 price_per_g 归一：20 元/kg = 0.02 元/g。
缺 50g 估价应为 50*0.02 = 1.0 元（旧 buy/500*price 会错算成 2.0 元）。
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="confirm_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 't.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.routers import planner  # noqa: E402
from app.services.pricing import price_per_g, cost_per_g, latest_price_map  # noqa: E402


def main():
    # ---- 纯函数：单位归一 ----
    assert abs(price_per_g(10, "元/500克") - 0.02) < 1e-9
    assert abs(price_per_g(20, "元/千克") - 0.02) < 1e-9
    assert abs(price_per_g(20, "元/kg") - 0.02) < 1e-9
    assert abs(price_per_g(15, "元/斤") - 0.03) < 1e-9      # 斤=500g
    assert abs(price_per_g(5, "参考价(电商)") - 0.01) < 1e-9  # 无规格按 500g
    assert abs(price_per_g(0.05, "元/克") - 0.05) < 1e-9
    print("[OK] price_per_g 单位归一正确")

    # ---- 成本护栏：电商「整件/打包参考价」不进成本，回退 base_price ----
    _gov = models.PriceRecord(ingredient_id=1, price=20.0, spec="元/千克",
                              date=date.today(), source="政府指导价")
    _ecom = models.PriceRecord(ingredient_id=2, price=2327.3, spec="参考价(电商)",
                               date=date.today(), source="电商平台参考价")
    assert abs(cost_per_g(_gov, 10.0) - 0.02) < 1e-9, "政府价 20元/kg 应=0.02元/g"
    assert abs(cost_per_g(_ecom, 5.0) - 0.01) < 1e-9, \
        "电商 2327 元整件价应被忽略，回退 base_price 5/500=0.01"
    assert abs(cost_per_g(None, 5.0) - 0.01) < 1e-9, "无记录回退 base_price"
    print("[OK] cost_per_g 成本护栏：只信政府价，电商整件价不进成本")

    # ---- 电商克重归一化后进成本 ----
    _ecom_norm = models.PriceRecord(ingredient_id=3, price=42.0, spec="元/500克",
                                    date=date.today(), source="电商平台参考价")
    assert abs(cost_per_g(_ecom_norm, 5.0) - 0.084) < 1e-6, \
        "电商归一化 42元/500克=0.084元/g（规格含'500克'→可信）"
    print("[OK] cost_per_g 电商归一化后进成本")

    # ---- 集成：confirm_plan 扣库存 + 缺量估价 ----
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    today = date.today()

    ing = models.Ingredient(name="大米", category="粮油", unit="g", base_price=10.0)
    db.add(ing)
    db.commit()
    r = models.Recipe(name="米饭", category="主食", meal_types=["lunch"],
                      steps=[], cook_minutes=20)
    db.add(r)
    db.flush()
    db.add(models.RecipeIngredient(recipe_id=r.id, ingredient_id=ing.id,
                                   amount=100, unit="g"))
    # 库存仅 50g（不足 100g）
    db.add(models.InventoryBatch(
        ingredient_id=ing.id, qty=50, remaining_qty=50, unit="g", unit_price=10,
        purchase_date=today, expire_date=today + timedelta(days=5)))
    plan = models.MealPlan(start_date=today, days=1, budget=100, mode="week",
                           status="draft")
    db.add(plan)
    db.flush()
    db.add(models.PlanMeal(plan_id=plan.id, date=today, meal_type="lunch",
                           recipe_id=r.id, servings=1, est_cost=0))
    # 真实价 20 元/千克 = 0.02 元/g
    db.add(models.PriceRecord(ingredient_id=ing.id, price=20.0, spec="元/千克",
                              date=today, source="政府指导价"))
    db.commit()

    res = planner.confirm_plan(plan.id, db=db)
    batch = db.scalars(select(models.InventoryBatch)).first()
    assert batch.remaining_qty == 0, f"应扣完 50g，剩 {batch.remaining_qty}"
    items = db.scalars(select(models.ShoppingItem)).all()
    assert len(items) == 1 and items[0].need_qty == 50, \
        f"缺量应为 50g，实际 {[(i.need_qty,) for i in items]}"
    assert abs(items[0].est_price - 1.0) < 0.01, \
        f"缺 50g 估价应 1.0 元，实际 {items[0].est_price}"
    print(f"[OK] confirm_plan：扣库存 50g，缺量 50g，估价 {items[0].est_price} 元"
          f"（元/kg 归一正确，未按 500g 错算 2 倍）")
    print("    返回:", res)
    db.close()
    print("\n✓ confirm_plan 与单位归一测试全部通过")


if __name__ == "__main__":
    main()
