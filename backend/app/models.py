"""SQLAlchemy ORM 模型 —— 覆盖食材/菜价/食谱/营养/计划/进销存/采购全部数据。"""
from datetime import date, datetime
from sqlalchemy import (
    String, Integer, Float, Boolean, Date, DateTime, ForeignKey, JSON, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Ingredient(Base):
    """食材表"""
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(20))  # 蔬菜/肉类/水产/蛋奶/粮油/豆制品/菌菇/调味/水果
    unit: Mapped[str] = mapped_column(String(10), default="g")  # g/ml/个
    icon: Mapped[str] = mapped_column(String(10), default="🥬")  # emoji 图标
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_shelf_life_days: Mapped[int] = mapped_column(Integer, default=7)
    storage_method: Mapped[str] = mapped_column(String(10), default="冷藏")  # 常温/冷藏/冷冻
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # 每 100g 营养（用于缺配料时的近似计算，可为空）
    protein_100g: Mapped[float] = mapped_column(Float, default=0)
    carb_100g: Mapped[float] = mapped_column(Float, default=0)
    fat_100g: Mapped[float] = mapped_column(Float, default=0)
    base_price: Mapped[float] = mapped_column(Float, default=5.0)  # 模拟引擎基准价 元/500g

    prices = relationship("PriceRecord", back_populates="ingredient")
    batches = relationship("InventoryBatch", back_populates="ingredient")


class PriceRecord(Base):
    """菜价记录表。

    唯一性由启动迁移在 (ingredient_id, date, source) 上建的唯一索引保证
    （见 database.migrate_schema），而非模型 __table_args__，以便兼容既有表。
    """
    __tablename__ = "price_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    price: Mapped[float] = mapped_column(Float)  # 元/500g（或 元/个）
    spec: Mapped[str] = mapped_column(String(20), default="500g")
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(50), default="模拟数据(演示)")
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # 价格原始凭证/商品链接（政府为文章页 URL，电商为搜索页 URL）
    ingredient = relationship("Ingredient", back_populates="prices")


class Recipe(Base):
    """食谱表"""
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(20))  # 主菜/副菜/主食/汤/早餐
    meal_types: Mapped[list] = mapped_column(JSON, default=list)  # ["breakfast","lunch","dinner"]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    cook_minutes: Mapped[int] = mapped_column(Integer, default=30)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 占位图/上传图
    # 单人份营养
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carb_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    kcal: Mapped[float] = mapped_column(Float, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, default=0)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # 需提前几小时备菜（腌制/泡发/发酵/过夜等），0 = 即做即食
    prep_ahead_hours: Mapped[int] = mapped_column(Integer, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    """食谱-食材关联（单人份用量）"""
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    amount: Mapped[float] = mapped_column(Float)  # 单人份用量
    unit: Mapped[str] = mapped_column(String(10), default="g")

    recipe = relationship("Recipe", back_populates="items")
    ingredient = relationship("Ingredient")


class NutritionTemplate(Base):
    """营养目标模板（可保存多套）"""
    __tablename__ = "nutrition_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    scope: Mapped[str] = mapped_column(String(10), default="daily")  # daily/weekly
    protein_g: Mapped[float] = mapped_column(Float, default=60)
    carb_g: Mapped[float] = mapped_column(Float, default=250)
    fat_g: Mapped[float] = mapped_column(Float, default=60)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)  # 可选微量营养素
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class MealSchedule(Base):
    """每周天餐次开关 + 每餐菜数（周一~周日各自独立配置）"""
    __tablename__ = "meal_schedule"

    id: Mapped[int] = mapped_column(primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, unique=True)  # 0=周一 ... 6=周日
    breakfast: Mapped[bool] = mapped_column(Boolean, default=True)
    lunch: Mapped[bool] = mapped_column(Boolean, default=True)
    dinner: Mapped[bool] = mapped_column(Boolean, default=True)
    lunch_courses: Mapped[int] = mapped_column(Integer, default=2)   # 午餐几道菜（1~4）
    dinner_courses: Mapped[int] = mapped_column(Integer, default=3)  # 晚餐几道菜（1~4）


class FamilySettings(Base):
    """家庭全局设置（单行）"""
    __tablename__ = "family_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    people: Mapped[int] = mapped_column(Integer, default=3)
    weekly_budget: Mapped[float] = mapped_column(Float, default=500)
    allergies: Mapped[list] = mapped_column(JSON, default=list)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    staple_type: Mapped[str] = mapped_column(String(20), default="米饭")     # 米饭/馒头/面条
    staple_per_person_g: Mapped[int] = mapped_column(Integer, default=150)   # 人均克数


class MealPlan(Base):
    """菜谱计划（周计划 / 长期计划）"""
    __tablename__ = "meal_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(Integer, default=7)
    budget: Mapped[float] = mapped_column(Float)
    total_cost: Mapped[float] = mapped_column(Float, default=0)
    mode: Mapped[str] = mapped_column(String(12), default="week")  # week/long_term
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft/confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    meals = relationship("PlanMeal", back_populates="plan", cascade="all, delete-orphan")


class PlanMeal(Base):
    """计划中的一餐"""
    __tablename__ = "plan_meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("meal_plans.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(10))  # breakfast/lunch/dinner
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    servings: Mapped[int] = mapped_column(Integer, default=3)
    est_cost: Mapped[float] = mapped_column(Float, default=0)
    done_status: Mapped[str] = mapped_column(String(10), default="pending")  # pending/done/skipped 饮食依从度统计

    plan = relationship("MealPlan", back_populates="meals")
    recipe = relationship("Recipe")


class InventoryBatch(Base):
    """库存批次表（"进"与"存"）"""
    __tablename__ = "inventory_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    qty: Mapped[float] = mapped_column(Float)          # 入库量
    remaining_qty: Mapped[float] = mapped_column(Float)  # 剩余量
    unit: Mapped[str] = mapped_column(String(10), default="g")
    unit_price: Mapped[float] = mapped_column(Float, default=0)  # 元/500g
    purchase_date: Mapped[date] = mapped_column(Date)
    expire_date: Mapped[date] = mapped_column(Date)
    storage_method: Mapped[str] = mapped_column(String(10), default="冷藏")
    location: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 存放位置：如"冷冻第二层"
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)

    ingredient = relationship("Ingredient", back_populates="batches")


class ConsumptionLog(Base):
    """消耗日志（"销"）"""
    __tablename__ = "consumption_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("inventory_batches.id"))
    qty: Mapped[float] = mapped_column(Float)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    reason: Mapped[str] = mapped_column(String(20), default="manual")  # plan/manual/discard
    plan_meal_id: Mapped[int | None] = mapped_column(ForeignKey("plan_meals.id"), nullable=True)


class ShoppingItem(Base):
    """采购清单项"""
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    need_qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10), default="g")
    est_price: Mapped[float] = mapped_column(Float, default=0)
    bought: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("meal_plans.id"), nullable=True)
    batch_no: Mapped[int] = mapped_column(Integer, default=1)  # 长期模式：第几批采购
    suggest_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 建议购买日
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    ingredient = relationship("Ingredient")
