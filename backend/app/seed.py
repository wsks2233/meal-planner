"""种子数据：食材、默认设置、演示库存（食谱仅来自 HowToCook 导入，菜价从启动日起真实记录）。"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select, func
from .database import SessionLocal, engine, Base
from . import models

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
        # 内置食谱(recipes.json)已取消：经用户确认，内置菜谱数据不准确，
        # 一切以第三方 HowToCook 导入为准。fresh 安装后需手动执行
        # scripts/import_howtocook.py 生成食谱，本函数不再写入任何 Recipe。

        # ---- 菜价 ----
        # 不预填历史：价格从启动日起由调度器真实抓取记录（fetch_today_prices）。
        # 首次启动的后台抓取写入启动当天真实价，之后每周一追加。

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
