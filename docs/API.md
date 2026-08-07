# 家庭智能膳食规划与进销存管理系统 · 后端 API 参考

> FastAPI 1.0.0 · SQLAlchemy 2.0 · Pydantic v2 · APScheduler
> 所有接口前缀为 `/api`，CORS 已放开（`allow_origins=["*"]`），无鉴权（家庭自用）。

## 0. 通用约定

| 项 | 说明 |
|---|---|
| Base URL | 开发 `http://127.0.0.1:8000`；生产经 nginx 反代 `/api` → `backend:8000` |
| 内容类型 | `application/json`（上传图片除外，用 `multipart/form-data`） |
| 鉴权 | 无（家庭局域网自用） |
| 错误 | HTTP 状态码 + `{"detail": "..."}`（前端 `axios` 拦截器取 `detail` 弹错） |
| 数据校验 | Pydantic v2 模型（`ORM` 基类开启 `from_attributes`，可直接由 ORM 对象序列化） |
| 静态资源 | `GET /uploads/<file>` 食谱成品图（由 `app.mount` 提供） |

### 健康检查
```
GET /api/health  →  {"status":"ok"}
```

### 跨域 / 时区
- CORS：`allow_methods=["*"]`、`allow_headers=["*"]`、`allow_credentials=True`。
- 价格、库存日期统一用 `date.isoformat()`（`YYYY-MM-DD`），服务端 `date.today()` 取服务器本地日期。

---

## 1. 菜价 Prices  `/api/prices`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/latest` | 每种食材最新价（含环比涨跌幅与可用性） |
| PATCH | `/{ingredient_id}/normalize` | 手动修正价格单位（克重描述 → 元/500克） |
| GET | `/source` | 当前价格源组成（政府价 / 电商兜底），供前端透明展示 |
| GET | `/trend/{ingredient_id}` | 价格趋势（按 `days` 控制周/月/季窗口） |

**GET /latest** 返回数组，每项：
```json
{
  "ingredient_id": 1, "name": "西红柿", "icon": "🍅", "category": "蔬菜",
  "price": 4.5, "spec": "元/500克", "date": "2026-08-06",
  "change_7d": -3.2,            // 环比上一期；窗口<2条时为 null（前端显示"—"，不臆造 0%）
  "source": "政府指导价",        // 或 "电商平台参考价" / "暂无可靠价"
  "available": true,            // false 时前端灰标
  "source_url": "https://..."   // 电商兜底时可能有原始凭证链接
}
```
- 无可靠价项的 `available=false`、`source="暂无可靠价"`、`price=null`、`change_7d=null`。

**PATCH /{ingredient_id}/normalize** 入参 `PriceNormalizeIn`：`{ "raw_weight": "5kg" }`（支持 `5kg/500g/1斤/2.5千克`）。
仅对当天记录生效，解析克重后归一化为「元/500克」；无当天记录 → 404，无法解析 → 400。返回 `{ok, old_price, old_spec, new_price, new_spec, parsed_weight_g}`。

**GET /trend/{ingredient_id}?days=30** 返回 `PriceTrendOut`：
```json
{ "ingredient_id":1, "ingredient_name":"西红柿",
  "dates":["2026-07-07",...], "prices":[4.8,4.6,...], "source":"政府指导价" }
```
`days` 范围 `1–365`，默认 30。

---

## 2. 食材 Ingredients  `/api/ingredients`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | ``（空路径） | 食材列表（按分类/关键字过滤） |
| GET | `/barcode/{code}` | 模拟扫码：按条形码查食材 |

**GET /** 查询参数：`category`（如 `蔬菜`）、`q`（名称模糊匹配）。返回 `IngredientOut[]`：
```json
{ "id":1, "name":"西红柿", "category":"蔬菜", "unit":"g", "icon":"🍅",
  "default_shelf_life_days":7, "storage_method":"冷藏", "barcode":null, "base_price":4.0 }
```

---

## 3. 食谱 Recipes  `/api/recipes`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `` | 食谱列表（分类/餐次/关键字/时长过滤） |
| GET | `/{recipe_id}` | 食谱详情（含配料 items） |
| POST | `` | 新建自定义食谱 |
| POST | `/{recipe_id}/image` | 上传成品图（`multipart`） |
| DELETE | `/{recipe_id}` | 删除（内置食谱不可删） |

**GET /** 查询参数：`category`、`meal_type`（`breakfast/lunch/dinner`）、`q`、`max_minutes`（≤ 该时长）。
**GET /{recipe_id}** 返回 `RecipeDetailOut`（含 `items: RecipeItemOut[]`，每项带 `ingredient_name`、`icon`）。

**POST /** 入参 `RecipeIn`：
```json
{ "name":"番茄炒蛋", "category":"主菜", "meal_types":["lunch","dinner"],
  "steps":["打蛋","下锅"], "cook_minutes":15,
  "protein_g":12, "carb_g":6, "fat_g":9, "kcal":180, "fiber_g":2,
  "tags":["快手"], "note":null, "prep_ahead_hours":0,
  "items":[{"ingredient_id":1,"amount":200,"unit":"g"}] }
```
同名已存在 → 400；内置食谱由种子数据灌入，`is_builtin=true`。

---

## 4. 设置 Settings  `/api/settings`

### 4.1 营养目标模板  `/settings/templates`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/templates` | 模板列表 |
| POST | `/templates` | 新建（设 `is_active` 会取消其它模板激活） |
| PUT | `/templates/{tid}` | 更新 |
| DELETE | `/templates/{tid}` | 删除 |

`NutritionTemplateIn`：`{name, scope("daily"|"weekly"), protein_g, carb_g, fat_g, fiber_g?, is_active}`。

### 4.2 每周餐次  `/settings/schedule`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/schedule` | 7 天餐次开关列表 |
| PUT | `/schedule` | 按周天批量更新（数组） |

`MealScheduleIn`：`{weekday(0–6), breakfast, lunch, dinner, lunch_courses(1–4), dinner_courses(1–4)}`。

### 4.3 家庭设置  `/settings/family`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/family` | 读取（不存在则自动建默认） |
| PUT | `/family` | 更新 |

`FamilySettingsIn`：`{people(默认3), weekly_budget(默认500), allergies:int[], notify_enabled, staple_type("米饭"), staple_per_person_g(50–500)}`。

---

## 5. 计划 Plans  `/api/plans`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/generate` | 生成周计划 / 长期计划（推荐引擎） |
| GET | `` | 最近 10 个计划列表 |
| GET | `/today` | 今日菜谱与所需食材（通知/手动入口） |
| GET | `/{plan_id}` | 计划详情（含每日每餐 meals） |
| GET | `/meals/{plan_meal_id}/replace-candidates` | 替换某餐的"代价最小"备选 |
| PUT | `/meals/{plan_meal_id}` | 替换食谱 / 标记完成状态 |
| POST | `/{plan_id}/confirm` | 确认计划：「销」库存 + 缺量写入采购清单 |

**POST /generate** 入参 `PlanGenerateIn`：
```json
{ "start_date":"2026-08-06", "days":7, "budget":null,
  "mode":"week",            // "week" | "long_term"
  "use_inventory":true, "template_id":null }
```
返回 `PlanGenerateOut`：`{feasible, plan:PlanOut|null, message, suggestions[], nutrition_report{}, staple{}}`。
- `feasible=false` 时返回放宽建议，**不落库**。
- 长期模式按 7 天分段生成，逐周保证 ≥70% 主菜轮换。
- `staple`：`{total_cost, per_person_g, ingredient_name}` 主食成本。

**GET /today** 返回 `[{meal_type, recipe, plan_meal_id, done_status, ingredients:[{name,amount,unit}]}]`，按早/午/晚排序，同餐次取最新计划。

**PUT /meals/{plan_meal_id}** 查询参数：`recipe_id?`、`done_status?`（`pending|done|skipped`）。用于替换食谱或标记饮食依从度。

**POST /{plan_id}/confirm** 返回 `{ok, shortage_count, message}`：按临期优先（FIFO by expire_date）扣减库存，缺量写入采购清单（长期模式按保质期分批并给建议购买日）。已确认过 → 400。

---

## 6. 库存 Inventory  `/api/inventory`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `` | 库存批次列表（按状态/存放方式过滤） |
| POST | `` | 采购入库（"进"） |
| POST | `/consume` | 手动记录消耗（"销"） |
| POST | `/{batch_id}/discard` | 标记丢弃（过期废弃） |
| POST | `/{batch_id}/to-shopping` | 一键加入购物清单（按原入库量补货） |

**GET /** 查询参数：`status`（`新鲜/临期/过期`）、`storage`（`常温/冷藏/冷冻`）。返回 `BatchOut[]`，每项附 `status`（新鲜/临期/过期）、`days_left`、`ingredient_name`、`icon`。

**POST /** 入参 `BatchIn`：`{ingredient_id, qty, unit("g"), unit_price, purchase_date, expire_date?, storage_method?, location?}`。缺保质期/存放方式时按食材默认值自动规划。

**POST /consume** 入参 `ConsumeIn`：`{batch_id, qty, reason("manual")}`；`qty<=0` → 400。

---

## 7. 采购 Shopping  `/api/shopping`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `` | 购物项列表 |
| POST | `/buy` | 批量标记已购买 / 取消 |
| POST | `/merge-pending` | 合并历史未购买项为一条新清单 |
| DELETE | `/{item_id}` | 删除单项 |
| GET | `/calendar.ics` | 采购日历 ICS 导出（可加入系统日历） |

**GET /** 查询参数：`only_pending`（仅未购）。返回 `ShoppingItemOut[]`：`{id, ingredient_id, need_qty, unit, est_price, bought, batch_no, suggest_date, ingredient_name, icon, storage_method}`。

**POST /buy** 入参 `BuyIn`：`{item_ids:[int], bought:bool}`。

**GET /calendar.ics?plan_id=** 返回 `text/calendar`，`Content-Disposition: attachment; filename=purchase-calendar.ics`。

---

## 8. 仪表盘 Dashboard  `/api/dashboard`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `` | 综合概览（首页一次性聚合） |

返回对象聚合多域数据：
```json
{
  "budget": {
    "budget":500, "total_cost":432.5, "spent_so_far":120,
    "mode":"week", "plan_id":1, "status":"confirmed",
    "usage_pct":86.5
  },
  "nutrition_rate": { "protein":92.1, "carb":78.4, "fat":105.2 },  // 近7天达标率%
  "adherence": 85.7,            // 饮食依从度%
  "expiring": [ { "batch_id":3, "name":"鸡蛋", "icon":"🥚",
                  "remaining_qty":6, "unit":"个", "days_left":1, "location":"冷藏" } ],
  "expiring_count": 2,
  "price_movers": [ { "ingredient_id":1, "name":"西红柿", "icon":"🍅",
                      "price":4.5, "change":-3.2, "spark":[4.8,4.6,...] } ],  // 异动前4
  "shopping_pending": true
}
```
- `nutrition_rate` 为 `null` 时无激活模板或未生成计划；`adherence` 无餐次时为 `null`。

---

## 9. 数据模型速览（后端 `models.py`）

| 模型 | 关键字段 | 关联 |
|---|---|---|
| Ingredient | id, name, category, unit, icon, default_shelf_life_days, storage_method, barcode, base_price | 1—* PriceRecord / InventoryBatch / RecipeIngredient / ShoppingItem |
| PriceRecord | ingredient_id, price, spec, date, source, source_url | *—1 Ingredient（唯一索引 ingredient_id+date） |
| Recipe | name, category, meal_types, steps, cook_minutes, image_url, 营养字段, tags, is_builtin, prep_ahead_hours | 1—* RecipeIngredient / PlanMeal |
| PlanMeal | plan_id, date, meal_type, recipe_id, servings, est_cost, done_status | *—1 Recipe / MealPlan |
| MealPlan | start_date, days, budget, total_cost, mode, status | 1—* PlanMeal |
| InventoryBatch | ingredient_id, qty, remaining_qty, unit, unit_price, purchase/expire_date, storage_method, location, discarded | 1—* ConsumptionLog |
| ShoppingItem | plan_id?, ingredient_id, need_qty, unit, est_price, bought, batch_no, suggest_date | *—1 Ingredient |
| NutritionTemplate / MealSchedule / FamilySettings | 见 §4 | — |
| ConsumptionLog | batch_id, qty, date, reason, plan_meal_id? | — |

---

## 10. 前端 API 封装对照（`frontend/src/api/index.js`）

前端 `api` 对象已 1:1 封装上述端点，例如 `api.dashboard()`、`api.latestPrices()`、`api.generatePlan(payload)`、`api.confirmPlan(id)`、`api.inventory(params)`、`api.markBought({item_ids, bought})` 等，`axios` 拦截器统一剥去 `response.data` 并弹错。

> 注：所有价格/库存日期由后端 `date.today()` 计算，前端无需时区处理。
