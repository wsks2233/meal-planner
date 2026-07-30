"""智能菜谱推荐引擎。

算法选择说明（复杂度与现实可行性）：
- 该问题本质是带预算/营养约束的组合选择问题（每个餐格从候选食谱中选一），
  属于整数规划范畴。严格解法可用 CSP 或 ILP（如 PuLP），但：
  1) 食谱是"整份"选择，营养/成本高度离散，LP 松弛意义有限；
  2) 家庭场景规模小（约 60 候选 x 21~42 餐格），启发式即可秒级得到高质量解；
  3) 启发式代码可读可维护，便于叠加"多样性/临期优先"等软约束。
- 因此采用：贪心构造（按评分逐格填充）+ 局部随机优化（简化模拟退火）。
- 复杂度：贪心 O(S x C)，局部优化 O(I x C)，S=餐格数、C=候选数、I=迭代次数。
  默认 I=400，总计算量 < 10^5 次评分，毫秒~百毫秒级。
"""
import math
import random
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..config import OPTIMIZER_ITERATIONS, EXPIRING_SOON_DAYS
from .pricing import latest_price_map, price_per_g, DEFAULT_PER_G

MEAL_TYPES = ["breakfast", "lunch", "dinner"]

# 评分权重
W_VALUE = 1.0      # 性价比（营养密度/成本）
W_NUTRI = 2.0      # 营养缺口贡献
W_EXPIRE = 1.5     # 临期食材消耗奖励
W_REPEAT = 3.0     # 重复惩罚


class Ctx:
    """一次推荐会话的上下文（价格、库存、候选、营养目标）。"""

    def __init__(self, db: Session, people: int, allergies: list[int],
                 use_inventory: bool, template: models.NutritionTemplate,
                 days: int):
        self.people = people
        self.days = days
        # 最新单价 {ingredient_id: 元/克} —— 单查询取每食材最新价并按规格归一，
        # 避免「每食材一次查询」的 N+1；无记录时回退 base_price（元/500g -> 元/克）。
        today = date.today()
        latest = latest_price_map(db)
        self.per_g: dict[int, float] = {}
        for ing in db.scalars(select(models.Ingredient)):
            rec = latest.get(ing.id)
            self.per_g[ing.id] = (price_per_g(rec.price, rec.spec)
                                  if rec else ing.base_price / 500.0)
        # 库存（虚拟扣减用的可变副本）与临期集合
        self.inventory: dict[int, float] = defaultdict(float)
        self.expiring: set[int] = set()
        if use_inventory:
            for b in db.scalars(select(models.InventoryBatch).where(
                    models.InventoryBatch.discarded == False,  # noqa: E712
                    models.InventoryBatch.remaining_qty > 0)):
                if b.expire_date >= today:
                    self.inventory[b.ingredient_id] += b.remaining_qty
                    if (b.expire_date - today).days <= EXPIRING_SOON_DAYS:
                        self.expiring.add(b.ingredient_id)
        # 候选食谱（剔除忌口）
        allergy_set = set(allergies or [])
        self.candidates: dict[str, list[models.Recipe]] = {m: [] for m in MEAL_TYPES}
        recipes = db.scalars(select(models.Recipe).options(
            selectinload(models.Recipe.items))).all()
        for r in recipes:
            if any(it.ingredient_id in allergy_set for it in r.items):
                continue
            for m in r.meal_types:
                if m in self.candidates:
                    self.candidates[m].append(r)
        # 营养目标（换算为全周期总量，人均 -> 全家）
        factor = days if template.scope == "daily" else max(1, days / 7)
        self.target = {
            "protein": template.protein_g * factor * people,
            "carb": template.carb_g * factor * people,
            "fat": template.fat_g * factor * people,
            "fiber": (template.fiber_g or 0) * factor * people,
        }

    def meal_cost(self, recipe: models.Recipe, inv: dict[int, float]) -> tuple[float, float]:
        """返回 (新增采购成本, 消耗临期食材克数)。inv 为虚拟库存（不修改）。

        成本按「元/克」单价计算（buy 为克数），消除过去 buy/500*price 对
        「元/500g」的硬编码假设，兼容 元/kg、元/斤、电商参考价等规格。
        """
        cost, expire_used = 0.0, 0.0
        for it in recipe.items:
            need = it.amount * self.people
            have = min(need, inv.get(it.ingredient_id, 0))
            buy = need - have
            cost += buy * self.per_g.get(it.ingredient_id, DEFAULT_PER_G)
            if it.ingredient_id in self.expiring:
                expire_used += have
        return cost, expire_used

    def consume(self, recipe: models.Recipe, inv: dict[int, float]):
        for it in recipe.items:
            need = it.amount * self.people
            take = min(need, inv.get(it.ingredient_id, 0))
            if take:
                inv[it.ingredient_id] = inv[it.ingredient_id] - take


def _nutrition_of(recipe: models.Recipe, people: int) -> dict:
    return {"protein": recipe.protein_g * people, "carb": recipe.carb_g * people,
            "fat": recipe.fat_g * people, "fiber": recipe.fiber_g * people}


def _plan_nutrition(assign: dict, people: int) -> dict:
    tot = {"protein": 0.0, "carb": 0.0, "fat": 0.0, "fiber": 0.0}
    for r in assign.values():
        n = _nutrition_of(r, people)
        for k in tot:
            tot[k] += n[k]
    return tot


def _deviation(total: dict, target: dict) -> float:
    """营养偏差：各项相对误差平方和（fiber 目标为 0 时忽略）。"""
    dev = 0.0
    for k, tgt in target.items():
        if tgt <= 0:
            continue
        dev += ((total[k] - tgt) / tgt) ** 2
    return dev


def generate_plan(db: Session, *, start_date: date, days: int, budget: float,
                  people: int, allergies: list[int], use_inventory: bool,
                  template: models.NutritionTemplate,
                  schedule: dict[int, dict[str, bool]],
                  prev_week_mains: set[int] | None = None) -> dict:
    """生成 days 天菜谱。返回 {feasible, slots, total_cost, nutrition_report, suggestions}。

    slots: [(date, meal_type, recipe, est_cost)]
    prev_week_mains: 长期模式下上一周主菜集合（用于 70% 轮换约束）。
    """
    ctx = Ctx(db, people, allergies, use_inventory, template, days)
    rng = random.Random(42)

    # 1) 展开餐格（按每周天餐次配置）
    slots: list[tuple[date, str]] = []
    for d in range(days):
        day = start_date + timedelta(days=d)
        conf = schedule.get(day.weekday(), {"breakfast": True, "lunch": True, "dinner": True})
        for m in MEAL_TYPES:
            if conf.get(m):
                slots.append((day, m))
    if not slots:
        return {"feasible": False, "message": "所有餐次均已关闭，请在设置中开启至少一餐",
                "slots": [], "total_cost": 0, "suggestions": [], "nutrition_report": {}}

    # 2) 贪心构造
    assign: dict[int, models.Recipe] = {}
    inv = dict(ctx.inventory)
    recent: list[models.Recipe] = []  # 近 3 天已选，用于重复惩罚
    running = {"protein": 0.0, "carb": 0.0, "fat": 0.0, "fiber": 0.0}
    total_cost = 0.0

    for idx, (day, meal) in enumerate(slots):
        cands = ctx.candidates.get(meal) or []
        if not cands:
            continue
        best, best_score = None, -math.inf
        for r in cands:
            cost, exp_used = ctx.meal_cost(r, inv)
            nutri = _nutrition_of(r, people)
            # 营养缺口贡献：越能填补当前缺口分越高
            gap_gain = sum(
                min(nutri[k], max(0, ctx.target[k] - running[k])) / ctx.target[k]
                for k in ctx.target if ctx.target[k] > 0)
            value = (r.protein_g + r.fiber_g * 2) / (cost + 1)  # 性价比
            repeat_pen = sum(1.0 for pr in recent if pr.id == r.id)
            repeat_pen += sum(0.4 for pr in recent
                              for a in pr.items for b in r.items
                              if a.ingredient_id == b.ingredient_id
                              and a.amount >= 80 and b.amount >= 80) / max(len(recent), 1)
            if prev_week_mains and r.category == "主菜" and r.id in prev_week_mains:
                repeat_pen += 2.0  # 长期模式：抑制与上周主菜重复（70% 轮换）
            score = (W_VALUE * value + W_NUTRI * gap_gain
                     + W_EXPIRE * (exp_used / 500) - W_REPEAT * repeat_pen
                     + rng.uniform(0, 0.15))
            if score > best_score:
                best, best_score = r, score
        assign[idx] = best
        cost, _ = ctx.meal_cost(best, inv)
        total_cost += cost
        ctx.consume(best, inv)
        n = _nutrition_of(best, people)
        for k in running:
            running[k] += n[k]
        recent.append(best)
        recent = recent[-9:]  # 约 3 天窗口

    # 3) 局部随机优化（简化模拟退火：只接受更优解）
    def evaluate(a: dict) -> tuple[float, float]:
        inv2 = dict(ctx.inventory)
        c = 0.0
        for i in sorted(a):
            mc, _ = ctx.meal_cost(a[i], inv2)
            c += mc
            ctx.consume(a[i], inv2)
        dev = _deviation(_plan_nutrition(a, people), ctx.target)
        return c, dev

    cur_cost, cur_dev = evaluate(assign)
    for _ in range(OPTIMIZER_ITERATIONS):
        i = rng.randrange(len(slots))
        if i not in assign:
            continue
        cands = ctx.candidates.get(slots[i][1]) or []
        if not cands:
            continue
        newr = rng.choice(cands)
        if newr.id == assign[i].id:
            continue
        old = assign[i]
        assign[i] = newr
        # 硬性多样性：同一天不出现重复食谱
        same_day_dup = any(j != i and slots[j][0] == slots[i][0]
                           and assign.get(j) and assign[j].id == newr.id
                           for j in range(len(slots)))
        nc, nd = evaluate(assign)
        over_old = max(0, cur_cost - budget)
        over_new = max(0, nc - budget)
        better = (over_new < over_old) or (over_new == over_old and nd < cur_dev)
        if better and not same_day_dup:
            cur_cost, cur_dev = nc, nd
        else:
            assign[i] = old

    # 4) 可行性判定与建议
    feasible = cur_cost <= budget
    suggestions = []
    if not feasible:
        gap = cur_cost - budget
        suggestions = [
            f"放宽预算 10%（约 ¥{budget * 1.1:.0f}，还差 ¥{gap:.0f}）",
            "下调蛋白质目标 15% 或改选'均衡饮食'模板",
            "减少高价肉类餐次（如将牛肉/海鲜替换为鸡胸肉、豆制品）",
        ]

    total_n = _plan_nutrition(assign, people)
    report = {
        "target": {k: round(v, 1) for k, v in ctx.target.items()},
        "actual": {k: round(v, 1) for k, v in total_n.items()},
        "achieve_rate": {
            k: round(total_n[k] / ctx.target[k] * 100, 1)
            for k in ctx.target if ctx.target[k] > 0},
    }

    # 5) 输出每格成本（重放一次得到逐餐成本）
    inv3 = dict(ctx.inventory)
    out_slots = []
    for i in sorted(assign):
        r = assign[i]
        mc, _ = ctx.meal_cost(r, inv3)
        ctx.consume(r, inv3)
        out_slots.append((slots[i][0], slots[i][1], r, round(mc, 2)))

    return {"feasible": feasible, "slots": out_slots, "total_cost": round(cur_cost, 2),
            "nutrition_report": report, "suggestions": suggestions,
            "message": "" if feasible else
            f"当前预算 ¥{budget:.0f} 无法满足营养目标（最优方案需 ¥{cur_cost:.0f}）"}


def replace_candidates(db: Session, plan_meal: models.PlanMeal, *, people: int,
                       allergies: list[int], limit: int = 5) -> list[dict]:
    """单餐替换：推荐"代价最小"的备选。

    代价 = 新增采购成本 + 食材相似度距离（相似食材越多代价越低，避免额外采购）
           + 营养偏移。
    """
    ctx = Ctx(db, people, allergies, True,
              models.NutritionTemplate(scope="daily", protein_g=1, carb_g=1, fat_g=1),
              1)
    orig = db.get(models.Recipe, plan_meal.recipe_id)
    orig_ings = {it.ingredient_id for it in orig.items}
    orig_n = _nutrition_of(orig, people)
    results = []
    for r in ctx.candidates.get(plan_meal.meal_type, []):
        if r.id == orig.id:
            continue
        cost, _ = ctx.meal_cost(r, dict(ctx.inventory))
        r_ings = {it.ingredient_id for it in r.items}
        sim_dist = 1 - len(orig_ings & r_ings) / max(len(orig_ings | r_ings), 1)
        n = _nutrition_of(r, people)
        shift = sum(abs(n[k] - orig_n[k]) for k in ("protein", "carb", "fat")) / 100
        penalty = cost + sim_dist * 5 + shift
        results.append({
            "recipe_id": r.id, "name": r.name, "category": r.category,
            "cook_minutes": r.cook_minutes, "est_cost": round(cost, 2),
            "similarity": round(1 - sim_dist, 2), "penalty": round(penalty, 2),
            "kcal": r.kcal, "protein_g": r.protein_g,
        })
    results.sort(key=lambda x: x["penalty"])
    return results[:limit]
