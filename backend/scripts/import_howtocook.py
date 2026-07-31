"""HowToCook 菜谱批量导入器。

用法（在 backend/ 目录下，使用项目 venv）：
  # 方式一：已有本地仓库
  venv/Scripts/python.exe scripts/import_howtocook.py --repo-path D:/repos/HowToCook

  # 方式二：自动浅克隆
  venv/Scripts/python.exe scripts/import_howtocook.py --clone

  # 只导入某分类 / 限量（用于先小规模验证）
  venv/Scripts/python.exe scripts/import_howtocook.py --repo-path ... --category vegetable_dish --limit 20

  # 不写库，仅统计+打印样例
  venv/Scripts/python.exe scripts/import_howtocook.py --repo-path ... --dry-run

  # 不克隆，直接实时抓取 N 篇真实菜谱解析（用于快速验证解析器）
  venv/Scripts/python.exe scripts/import_howtocook.py --live-sample 5

导入内容：Recipe（菜谱+步骤+难度+卡路里+时长）、Ingredient（材料中未收录的自动建表）、
RecipeIngredient（按「一份够 N 人」折算成单人份用量）。幂等：同名内置菜谱重复导入会更新。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.recipe_source import (  # noqa: E402
    CATEGORY_MAP, ING_CATEGORY_MAP, HowToCookParser,
)

REPO_API = "https://api.github.com/repos/Anduin2017/HowToCook"
REPO_HTTPS = "https://github.com/Anduin2017/HowToCook.git"


def _norm(name: str) -> str:
    return name.replace(" ", "").lower()


def _prep_hours_from_steps(steps):
    """根据步骤文本推算需提前几小时备菜（腌制/泡发/发酵/过夜）。0=即做。"""
    text = " ".join(steps or [])
    if any(k in text for k in ("过夜", "隔夜", "一夜", "冷藏一夜", "腌制一夜", "泡一夜", "浸泡过夜")):
        return 12
    if any(k in text for k in ("腌制", "腌渍", "腌入味", "抓腌", "腌一下", "腌制备")):
        return 4
    if any(k in text for k in ("泡发", "泡一", "泡开", "泡软", "浸泡", "发木耳", "发香菇", "发泡", "冷水泡")):
        return 4
    if any(k in text for k in ("发酵", "醒发", "醒面", "饧", "揉匀醒", "二次发酵", "冷藏发酵")):
        return 2
    return 0


def _list_repo_md(repo_path: str):
    """返回 [(folder, abs_path)]，遍历 dishes 下所有 .md（跳过 template）。"""
    out = []
    dishes = os.path.join(repo_path, "dishes")
    if not os.path.isdir(dishes):
        return out
    for folder in sorted(os.listdir(dishes)):
        fdir = os.path.join(dishes, folder)
        if not os.path.isdir(fdir) or folder == "template":
            continue
        for fn in sorted(os.listdir(fdir)):
            if fn.lower().endswith(".md"):
                out.append((folder, os.path.join(fdir, fn)))
    return out


def _live_sample(n: int):
    """实时抓取 N 篇真实菜谱解析并打印（不写库）。"""
    import json
    import urllib.request

    print(f"== 实时抓取 HowToCook 树（1 次 API 调用）==")
    tree_url = f"{REPO_API}/git/trees/master?recursive=1"
    try:
        data = json.loads(urllib.request.urlopen(tree_url, timeout=30).read())
    except Exception as e:  # noqa: BLE001
        print("API 调用失败：", e)
        return
    md = [t["path"] for t in data.get("tree", [])
          if t["path"].startswith("dishes/") and t["path"].endswith(".md")
          and "/template/" not in t["path"]]
    print(f"仓库共 {len(md)} 个菜谱 Markdown，取前 {n} 个解析：\n")
    parser = HowToCookParser()
    for path in md[:n]:
        raw = "https://raw.githubusercontent.com/Anduin2017/HowToCook/master/" + urllib.parse.quote(path)
        try:
            text = urllib.request.urlopen(raw, timeout=25).read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"[跳过] {path} 抓取失败：{e}")
            continue
        folder = path.split("/")[1]
        p = parser.parse(text, folder)
        print(f"▶ {p.name}  [{p.category}]  难度{p.difficulty}  卡路里{p.kcal}"
              f"  时长{p.cook_minutes}min  步骤{len(p.steps)}  食材{len(p.ingredients)}")
        for ing in p.ingredients[:6]:
            print(f"    - {ing.raw_name}: {ing.amount} {ing.unit}")
        if len(p.ingredients) > 6:
            print(f"    … 共 {len(p.ingredients)} 种")


def import_repo(repo_path: str, *, category=None, limit=None, dry_run=False):
    from sqlalchemy import select
    from app.database import SessionLocal
    from app import models

    files = _list_repo_md(repo_path)
    if category:
        files = [f for f in files if f[0] == category]
    if limit:
        files = files[:limit]

    print(f"待解析文件：{len(files)}")
    parser = HowToCookParser()
    recipes = []  # (ParsedRecipe, folder)
    for folder, fp in files:
        try:
            text = open(fp, encoding="utf-8").read()
        except Exception as e:  # noqa: BLE001
            print(f"[跳过] {fp}: {e}")
            continue
        try:
            recipes.append((parser.parse(text, folder), folder))
        except Exception as e:  # noqa: BLE001
            print(f"[解析失败] {fp}: {e}")

    print(f"成功解析：{len(recipes)} 道菜")

    if dry_run:
        for r, _ in recipes[:10]:
            print(f"  - {r.name} [{r.category}] 食材{len(r.ingredients)} 步骤{len(r.steps)}")
        print("（dry-run，未写入数据库）")
        return

    db = SessionLocal()
    try:
        # 建立食材名->id 索引（含已存在 + 本次新建）
        name2ing = {_norm(i.name): i for i in db.scalars(select(models.Ingredient)).all()}
        created_ing = 0
        recipe_upsert = 0
        item_writes = 0

        for r, folder in recipes:
            # 单人份折算：一份够 N 人 -> 用量/kcal 除以 N
            div = r.servings_hint if (r.servings_hint and r.servings_hint > 1) else 1

            # 解析食材 -> 关联 Ingredient（未知则建表）
            ing_links = []
            for pi in r.ingredients:
                key = _norm(pi.raw_name)
                ing = name2ing.get(key)
                if ing is None:
                    ing = models.Ingredient(
                        name=pi.raw_name,
                        category=ING_CATEGORY_MAP.get(folder, "其他"),
                        unit=pi.unit, icon="🥬", base_price=5.0,
                    )
                    db.add(ing)
                    db.flush()
                    name2ing[key] = ing
                    created_ing += 1
                ing_links.append((ing, pi.amount / div, pi.unit))

            # 食谱 upsert
            existing = db.scalars(
                select(models.Recipe).where(models.Recipe.name == r.name)).first()
            if existing and not existing.is_builtin:
                # 不覆盖用户自定义食谱
                continue
            kcal = round(r.kcal / div, 1) if div > 1 else r.kcal
            if existing:
                rec = existing
                rec.category = r.category
                rec.meal_types = r.meal_types
                rec.steps = r.steps
                rec.prep_ahead_hours = _prep_hours_from_steps(r.steps)
                rec.cook_minutes = r.cook_minutes or rec.cook_minutes
                rec.kcal = kcal
                rec.tags = [f"难度{r.difficulty}", "HowToCook"]
                rec.note = r.note
                # 清空旧用量，重写
                for old in list(rec.items):
                    db.delete(old)
                db.flush()
            else:
                rec = models.Recipe(
                    name=r.name, category=r.category, meal_types=r.meal_types,
                    steps=r.steps, prep_ahead_hours=_prep_hours_from_steps(r.steps),
                    cook_minutes=r.cook_minutes or 30,
                    kcal=kcal, tags=[f"难度{r.difficulty}", "HowToCook"], note=r.note,
                    is_builtin=True,
                )
                db.add(rec)
                db.flush()
            for ing, amount, unit in ing_links:
                db.add(models.RecipeIngredient(
                    recipe_id=rec.id, ingredient_id=ing.id,
                    amount=round(amount, 3), unit=unit))
                item_writes += 1
            recipe_upsert += 1

        db.commit()
        print(f"导入完成：食谱 {recipe_upsert} 道，新建食材 {created_ing} 种，"
              f"写入食谱-食材关联 {item_writes} 条。")
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser(description="HowToCook 菜谱导入器")
    ap.add_argument("--repo-path", help="本地 HowToCook 仓库路径")
    ap.add_argument("--clone", action="store_true", help="自动浅克隆到临时目录")
    ap.add_argument("--category", help="仅导入某分类，如 vegetable_dish")
    ap.add_argument("--limit", type=int, help="最多导入 N 个文件")
    ap.add_argument("--dry-run", action="store_true", help="只解析不写库")
    ap.add_argument("--live-sample", type=int, metavar="N",
                    help="实时抓取 N 篇真实菜谱解析（不写库）")
    args = ap.parse_args()

    if args.live_sample:
        _live_sample(args.live_sample)
        return

    repo_path = args.repo_path
    if not repo_path and args.clone:
        tmp = tempfile.mkdtemp(prefix="howtocook_")
        print(f"浅克隆到 {tmp} ...")
        subprocess.run(["git", "clone", "--depth", "1", REPO_HTTPS, tmp], check=True)
        repo_path = tmp
    if not repo_path or not os.path.isdir(repo_path):
        print("请提供 --repo-path 或 --clone。")
        sys.exit(1)

    import_repo(repo_path, category=args.category, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
