"""种子数据：食材、食谱、菜价历史回填、默认设置、演示库存。"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select, func
from .database import SessionLocal, engine, Base
from . import models
from .config import PRICE_BACKFILL_DAYS
from .services.price_engine import MockPriceSource

DATA_DIR = Path(__file__).parent / "data"


def seed_all():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.scalar(select(func.count(models.Ingredient.id))):
            return  # 已初始化
        # ---- 食材 ----
        raw = json.loads((DATA_DIR / "ingredients.json").read_text(encoding="utf-8"))
        name2ing = {}
        for i, r in enumerate(raw):
            ing = models.Ingredient(
                name=r["name"], category=r["category"], unit=r["unit"], icon=r["icon"],
                default_shelf_life_days=r["shelf_life"], storage_method=r["storage"],
                protein_100g=r["protein"], carb_100g=r["carb"], fat_100g=r["fat"],
                base_price=r["base_price"],
                barcode=f"69{100000000 + i}",  # 模拟条形码，方便扫码演示
            )
            db.add(ing)
            name2ing[r["name"]] = ing
        db.flush()

        # ---- 食谱 ----
        rraw = json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))
        for r in rraw:
            rec = models.Recipe(
                name=r["name"], category=r["category"], meal_types=r["meal_types"],
                steps=r["steps"], cook_minutes=r["cook"],
                protein_g=r["protein"], carb_g=r["carb"], fat_g=r["fat"],
                kcal=r["kcal"], fiber_g=r["fiber"], tags=r["tags"], is_builtin=True,
                image_url=f"/placeholder/{r['name']}.jpg",  # 图片占位符
            )
            db.add(rec)
            db.flush()
            for name, amount in r["items"]:
                ing = name2ing[name]
                db.add(models.RecipeIngredient(
                    recipe_id=rec.id, ingredient_id=ing.id, amount=amount, unit=ing.unit))

        # ---- 菜价历史回填（模拟引擎，90 天） ----
        src = MockPriceSource()
        today = date.today()
        for ing in name2ing.values():
            for d in range(PRICE_BACKFILL_DAYS, -1, -1):
                day = today - timedelta(days=d)
                db.add(models.PriceRecord(
                    ingredient_id=ing.id, price=src.price_for(ing.base_price, ing.id, day),
                    spec=f"500{ing.unit}" if ing.unit != "个" else "1个",
                    date=day, source="模拟数据(演示)"))

        # ---- 默认设置 ----
        db.add(models.FamilySettings(people=3, weekly_budget=500, allergies=[]))
        for wd in range(7):
            db.add(models.MealSchedule(weekday=wd, breakfast=True, lunch=True, dinner=True))
        db.add(models.NutritionTemplate(
            name="均衡饮食(默认)", scope="daily", protein_g=65, carb_g=250, fat_g=60,
            fiber_g=25, is_active=True))
        db.add(models.NutritionTemplate(
            name="高蛋白健身", scope="daily", protein_g=100, carb_g=200, fat_g=50, fiber_g=30))

        # ---- 演示库存（含新鲜/临期批次，便于演示临期优先消耗） ----
        demo = [
            ("大米", 5000, 60, "米缸"), ("鸡蛋", 900, 20, "冷藏门架"),
            ("土豆", 1500, 20, "阴凉角落"), ("猪五花肉", 500, 2, "冷藏第一层"),
            ("番茄", 600, 3, "冷藏第二层"), ("西兰花", 300, 2, "冷藏第二层"),
            ("冻虾仁", 400, 120, "冷冻第二层"), ("食用油", 2000, 300, "橱柜"),
        ]
        for name, qty, days_left, loc in demo:
            ing = name2ing[name]
            db.add(models.InventoryBatch(
                ingredient_id=ing.id, qty=qty, remaining_qty=qty, unit=ing.unit,
                unit_price=ing.base_price,
                purchase_date=today - timedelta(days=2),
                expire_date=today + timedelta(days=days_left),
                storage_method=ing.storage_method, location=loc))
        db.commit()
        print(f"Seeded: {len(name2ing)} ingredients, {len(rraw)} recipes")
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
