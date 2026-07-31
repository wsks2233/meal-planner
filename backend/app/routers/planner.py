from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas
from ..services import recommender
from ..services.long_term import batch_shopping_plan
from ..services.pricing import latest_price_map, cost_per_g

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _settings(db: Session) -> models.FamilySettings:
    s = db.scalars(select(models.FamilySettings)).first()
    if not s:
        s = models.FamilySettings()
        db.add(s)
        db.commit()
    return s


def _schedule_map(db: Session) -> dict[int, dict]:
    return {r.weekday: {
        "breakfast": r.breakfast, "lunch": r.lunch, "dinner": r.dinner,
        "lunch_courses": r.lunch_courses, "dinner_courses": r.dinner_courses,
    } for r in db.scalars(select(models.MealSchedule))}


def _template(db: Session, template_id: int | None) -> models.NutritionTemplate:
    if template_id:
        t = db.get(models.NutritionTemplate, template_id)
        if t:
            return t
    t = db.scalars(select(models.NutritionTemplate)
                   .where(models.NutritionTemplate.is_active == True)).first()  # noqa: E712
    return t or models.NutritionTemplate(name="默认", scope="daily",
                                         protein_g=65, carb_g=250, fat_g=60)


def plan_out(plan: models.MealPlan, db: Session) -> schemas.PlanOut:
    out = schemas.PlanOut.model_validate(plan)
    metas = {}
    for pm, po in zip(plan.meals, out.meals):
        if pm.recipe_id not in metas:
            metas[pm.recipe_id] = db.get(models.Recipe, pm.recipe_id)
        r = metas[pm.recipe_id]
        po.recipe_name, po.cook_minutes, po.image_url = r.name, r.cook_minutes, r.image_url
    return out


@router.post("/generate", response_model=schemas.PlanGenerateOut)
def generate(payload: schemas.PlanGenerateIn, db: Session = Depends(get_db)):
    """生成周计划或长期计划。

    长期模式按周分段生成，并传入上一周主菜集合实现每周 >=70% 主菜轮换。
    预算不可行时返回 feasible=False + 放宽建议，不落库。
    """
    s = _settings(db)
    schedule = _schedule_map(db)
    template = _template(db, payload.template_id)
    days = payload.days if payload.mode == "long_term" else min(payload.days, 7)
    budget = payload.budget or s.weekly_budget / 7 * days

    # 主食配置：找「大米」或其他主食食材，取其最新价
    staple = db.scalars(
        select(models.Ingredient).where(models.Ingredient.name.in_(("大米", "面粉", "挂面")))
    ).first()

    all_slots, total_cost = [], 0.0
    staple_info = {}
    reports, suggestions, feasible = [], [], True
    prev_mains: set[int] = set()
    offset = 0
    while offset < days:
        seg_days = min(7, days - offset)
        seg_budget = budget / days * seg_days
        res = recommender.generate_plan(
            db, start_date=payload.start_date + timedelta(days=offset),
            days=seg_days, budget=seg_budget, people=s.people,
            allergies=s.allergies or [], use_inventory=payload.use_inventory,
            template=template, schedule=schedule,
            staple_per_person_g=s.staple_per_person_g,
            staple_ingredient_id=staple.id if staple else None,
            prev_week_mains=prev_mains if payload.mode == "long_term" else None)
        if not res["slots"] and not res["feasible"]:
            return schemas.PlanGenerateOut(feasible=False, message=res["message"],
                                           suggestions=res["suggestions"])
        feasible = feasible and res["feasible"]
        suggestions = suggestions or res["suggestions"]
        total_cost += res["total_cost"]
        all_slots.extend(res["slots"])
        reports.append(res["nutrition_report"])
        if not staple_info:
            staple_info = res.get("staple", {})
        # slots: (date, meal_type, course_index, recipe, cost)
        prev_mains = {r.id for (_, _, _, r, _) in res["slots"] if r.category == "主菜"}
        offset += seg_days

    if not feasible:
        return schemas.PlanGenerateOut(
            feasible=False,
            message=f"当前预算 ¥{budget:.0f} 无法满足��养目标（方案最低需 ¥{total_cost:.0f}）",
            suggestions=suggestions, nutrition_report=reports[0] if reports else {})

    plan = models.MealPlan(start_date=payload.start_date, days=days, budget=budget,
                           total_cost=round(total_cost, 2), mode=payload.mode)
    db.add(plan)
    db.flush()
    for (d, meal, _course, recipe, cost) in all_slots:
        db.add(models.PlanMeal(plan_id=plan.id, date=d, meal_type=meal,
                               recipe_id=recipe.id, servings=s.people, est_cost=cost))
    db.commit()
    db.refresh(plan)
    return schemas.PlanGenerateOut(feasible=True, plan=plan_out(plan, db),
                                   staple=staple_info,
                                   nutrition_report=reports[0] if reports else {})


@router.get("", response_model=list[schemas.PlanOut])
def list_plans(db: Session = Depends(get_db)):
    plans = db.scalars(select(models.MealPlan)
                       .options(selectinload(models.MealPlan.meals))
                       .order_by(models.MealPlan.id.desc()).limit(10)).all()
    return [plan_out(p, db) for p in plans]


@router.get("/today")
def today_meals(db: Session = Depends(get_db)):
    """今日菜谱与所需食材（供每日 8 点通知/手动查看入口）。"""
    today = date.today()
    meals = db.scalars(select(models.PlanMeal)
                       .where(models.PlanMeal.date == today)
                       .order_by(models.PlanMeal.id.desc())).all()
    seen, out = set(), []
    for pm in meals:  # 同一餐次取最新计划
        if pm.meal_type in seen:
            continue
        seen.add(pm.meal_type)
        r = db.get(models.Recipe, pm.recipe_id)
        out.append({
            "meal_type": pm.meal_type, "recipe": r.name, "plan_meal_id": pm.id,
            "done_status": pm.done_status,
            "ingredients": [
                {"name": it.ingredient.name, "amount": it.amount * pm.servings,
                 "unit": it.unit} for it in r.items],
        })
    order = {"breakfast": 0, "lunch": 1, "dinner": 2}
    out.sort(key=lambda x: order.get(x["meal_type"], 9))
    return out


@router.get("/{plan_id}", response_model=schemas.PlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    p = db.scalars(select(models.MealPlan).where(models.MealPlan.id == plan_id)
                   .options(selectinload(models.MealPlan.meals))).first()
    if not p:
        raise HTTPException(404, "计划不存在")
    return plan_out(p, db)


@router.get("/meals/{plan_meal_id}/replace-candidates", response_model=schemas.ReplaceOut)
def replace_cands(plan_meal_id: int, db: Session = Depends(get_db)):
    """替换某餐时推荐"代价最小"的备选。"""
    pm = db.get(models.PlanMeal, plan_meal_id)
    if not pm:
        raise HTTPException(404, "餐次不存在")
    s = _settings(db)
    return schemas.ReplaceOut(candidates=recommender.replace_candidates(
        db, pm, people=s.people, allergies=s.allergies or []))


@router.put("/meals/{plan_meal_id}")
def update_meal(plan_meal_id: int, recipe_id: int | None = None,
                done_status: str | None = None, db: Session = Depends(get_db)):
    """替换食谱 / 标记完成状态（饮食依从度统计）。"""
    pm = db.get(models.PlanMeal, plan_meal_id)
    if not pm:
        raise HTTPException(404, "餐次不存在")
    if recipe_id:
        if not db.get(models.Recipe, recipe_id):
            raise HTTPException(404, "食谱不存在")
        pm.recipe_id = recipe_id
    if done_status in ("pending", "done", "skipped"):
        pm.done_status = done_status
    db.commit()
    return {"ok": True}


@router.post("/{plan_id}/confirm")
def confirm_plan(plan_id: int, db: Session = Depends(get_db)):
    """确认计划："销" —— 按临期优先(FIFO by expire_date)自动扣减库存，
    缺量部分自动写入采购清单（长期模式按保质期分批并给出建议购买日）。
    """
    plan = db.scalars(select(models.MealPlan).where(models.MealPlan.id == plan_id)
                      .options(selectinload(models.MealPlan.meals))).first()
    if not plan:
        raise HTTPException(404, "计划不存在")
    if plan.status == "confirmed":
        raise HTTPException(400, "计划已确认过")

    # 预载（消除循环内 N+1）：食谱(含配料)、全部有效批次按食材分组、食材、最新单价
    recipes = {r.id: r for r in db.scalars(
        select(models.Recipe).options(selectinload(models.Recipe.items)))}
    batches_by_ing: dict[int, list[models.InventoryBatch]] = defaultdict(list)
    for b in db.scalars(
            select(models.InventoryBatch)
            .where(models.InventoryBatch.discarded == False,  # noqa: E712
                   models.InventoryBatch.remaining_qty > 0,
                   models.InventoryBatch.expire_date >= date.today())
            .order_by(models.InventoryBatch.expire_date)):
        batches_by_ing[b.ingredient_id].append(b)

    shortages: dict[int, float] = defaultdict(float)
    for pm in plan.meals:
        recipe = recipes.get(pm.recipe_id)
        if not recipe:
            continue
        for it in recipe.items:
            need = it.amount * pm.servings
            for b in batches_by_ing.get(it.ingredient_id, []):
                if need <= 0:
                    break
                if b.remaining_qty <= 0:
                    continue
                take = min(need, b.remaining_qty)
                b.remaining_qty -= take
                need -= take
                db.add(models.ConsumptionLog(batch_id=b.id, qty=take,
                                             date=pm.date, reason="plan",
                                             plan_meal_id=pm.id))
            if need > 0:
                shortages[it.ingredient_id] += need

    # 缺量 → 采购清单
    if plan.mode == "long_term":
        for item in batch_shopping_plan(db, plan, plan.meals[0].servings if plan.meals else 3):
            item.pop("storage_method", None)  # 展示字段，非落库字段
            db.add(models.ShoppingItem(plan_id=plan.id, **item))
    else:
        ingredients = {i.id: i for i in db.scalars(select(models.Ingredient))}
        latest = latest_price_map(db)  # 单查询取每食材最新价（替代循环内逐食材查询）
        for ing_id, qty in shortages.items():
            ing = ingredients.get(ing_id)
            if not ing:
                continue
            rec = latest.get(ing_id)
            # 缺量估价同走成本护栏：只信任政府指导价，电商整件价/base_price 兜底
            per_g = cost_per_g(rec, ing.base_price)
            db.add(models.ShoppingItem(
                plan_id=plan.id, ingredient_id=ing_id, need_qty=round(qty, 0),
                unit=ing.unit, est_price=round(qty * per_g, 2),
                suggest_date=plan.start_date))
    plan.status = "confirmed"
    db.commit()
    return {"ok": True, "shortage_count": len(shortages),
            "message": f"库存已扣减，{len(shortages)} 种食材缺量已加入采购清单"
            if shortages else "库存已扣减，无缺量"}
