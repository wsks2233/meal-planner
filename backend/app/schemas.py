"""Pydantic v2 数据校验模型。"""
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 食材 & 菜价 ----------
class IngredientOut(ORM):
    id: int
    name: str
    category: str
    unit: str
    icon: str
    default_shelf_life_days: int
    storage_method: str
    barcode: str | None = None
    base_price: float


class PriceRecordOut(ORM):
    id: int
    ingredient_id: int
    price: float
    spec: str
    date: date
    source: str


class PriceTrendOut(BaseModel):
    ingredient_id: int
    ingredient_name: str
    dates: list[str]
    prices: list[float]
    source: str


class PriceNormalizeIn(BaseModel):
    """手动修正价格单位：用户输入克重描述。"""
    raw_weight: str = Field(..., min_length=1, max_length=80,
                            description="重量描述，如 5kg、500g、1斤、2.5千克")


# ---------- 食谱 ----------
class RecipeItemIn(BaseModel):
    ingredient_id: int
    amount: float
    unit: str = "g"


class RecipeItemOut(ORM):
    ingredient_id: int
    amount: float
    unit: str
    ingredient_name: str | None = None
    icon: str | None = None


class RecipeIn(BaseModel):
    name: str
    category: str = "主菜"
    meal_types: list[str] = ["lunch", "dinner"]
    steps: list[str] = []
    cook_minutes: int = 30
    protein_g: float = 0
    carb_g: float = 0
    fat_g: float = 0
    kcal: float = 0
    fiber_g: float = 0
    tags: list[str] = []
    note: str | None = None
    items: list[RecipeItemIn] = []


class RecipeOut(ORM):
    id: int
    name: str
    category: str
    meal_types: list
    steps: list
    cook_minutes: int
    image_url: str | None
    protein_g: float
    carb_g: float
    fat_g: float
    kcal: float
    fiber_g: float
    tags: list
    is_builtin: bool
    note: str | None = None


class RecipeDetailOut(RecipeOut):
    items: list[RecipeItemOut] = []


# ---------- 营养 & 设置 ----------
class NutritionTemplateIn(BaseModel):
    name: str
    scope: str = "daily"
    protein_g: float = 60
    carb_g: float = 250
    fat_g: float = 60
    fiber_g: float | None = None
    is_active: bool = False


class NutritionTemplateOut(NutritionTemplateIn, ORM):
    id: int


class MealScheduleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    breakfast: bool = True
    lunch: bool = True
    dinner: bool = True
    lunch_courses: int = Field(default=2, ge=1, le=4)
    dinner_courses: int = Field(default=3, ge=1, le=4)


class MealScheduleOut(MealScheduleIn, ORM):
    id: int


class FamilySettingsIn(BaseModel):
    people: int = 3
    weekly_budget: float = 500
    allergies: list[int] = []
    notify_enabled: bool = False
    staple_type: str = "米饭"
    staple_per_person_g: int = Field(default=150, ge=50, le=500)


class FamilySettingsOut(FamilySettingsIn, ORM):
    id: int


# ---------- 计划 ----------
class PlanGenerateIn(BaseModel):
    start_date: date
    days: int = 7
    budget: float | None = None      # 不传则用家庭设置里的周预算按天折算
    mode: str = "week"               # week / long_term
    use_inventory: bool = True
    template_id: int | None = None   # 营养模板，不传用 is_active 的


class PlanMealOut(ORM):
    id: int
    date: date
    meal_type: str
    recipe_id: int
    servings: int
    est_cost: float
    done_status: str
    recipe_name: str | None = None
    cook_minutes: int | None = None
    image_url: str | None = None


class PlanOut(ORM):
    id: int
    start_date: date
    days: int
    budget: float
    total_cost: float
    mode: str
    status: str
    meals: list[PlanMealOut] = []


class PlanGenerateOut(BaseModel):
    feasible: bool
    plan: PlanOut | None = None
    message: str = ""
    suggestions: list[str] = []
    nutrition_report: dict = {}
    staple: dict = {}              # 主食信息：{total_cost, per_person_g, ingredient_name}


class ReplaceOut(BaseModel):
    candidates: list[dict]           # 代价最小的备选列表


# ---------- 库存 ----------
class BatchIn(BaseModel):
    ingredient_id: int
    qty: float
    unit: str = "g"
    unit_price: float = 0
    purchase_date: date
    expire_date: date | None = None  # 不传则按食材默认保质期计算
    storage_method: str | None = None
    location: str | None = None


class BatchOut(ORM):
    id: int
    ingredient_id: int
    qty: float
    remaining_qty: float
    unit: str
    unit_price: float
    purchase_date: date
    expire_date: date
    storage_method: str
    location: str | None
    discarded: bool
    ingredient_name: str | None = None
    icon: str | None = None
    status: str | None = None        # 新鲜/临期/过期
    days_left: int | None = None


class ConsumeIn(BaseModel):
    batch_id: int
    qty: float
    reason: str = "manual"


# ---------- 采购 ----------
class ShoppingItemOut(ORM):
    id: int
    ingredient_id: int
    need_qty: float
    unit: str
    est_price: float
    bought: bool
    batch_no: int
    suggest_date: date | None
    ingredient_name: str | None = None
    icon: str | None = None
    storage_method: str | None = None


class BuyIn(BaseModel):
    item_ids: list[int]
    bought: bool = True
