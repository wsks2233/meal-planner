"""食谱导入器数据库集成测试（写入链路 + 幂等）。

不依赖网络/真实仓库：用两份内置 Markdown 搭临时仓库，写到临时 SQLite，
验证 Recipe / Ingredient（自动建表）/ RecipeIngredient（单人份折算）写入与重复导入幂等。
"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在导入任何 app 模块前固定测试库
_TMP = tempfile.mkdtemp(prefix="meal_recipe_db_")
_DB = os.path.join(_TMP, "recipe_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"

from sqlalchemy import create_engine, select  # noqa: E402

from app.database import SessionLocal, Base  # noqa: E402
from app import models  # noqa: E402
from tests.test_recipe_source import LIANG_BAN_HUANG_GUA, TEMPLATE  # noqa: E402
import scripts.import_howtocook as imp  # noqa: E402


def _build_tmp_repo():
    repo = tempfile.mkdtemp(prefix="htc_repo_")
    veg = os.path.join(repo, "dishes", "vegetable_dish")
    meat = os.path.join(repo, "dishes", "meat_dish")
    os.makedirs(veg, exist_ok=True)
    os.makedirs(meat, exist_ok=True)
    with open(os.path.join(veg, "凉拌黄瓜.md"), "w", encoding="utf-8") as f:
        f.write(LIANG_BAN_HUANG_GUA)
    # 示例菜模板：一份够 2 人 -> 单人份应折半
    with open(os.path.join(meat, "示例菜.md"), "w", encoding="utf-8") as f:
        f.write(TEMPLATE)
    return repo


def test_import_and_idempotent():
    Base.metadata.create_all(create_engine(os.environ["DATABASE_URL"]))
    repo = _build_tmp_repo()
    try:
        imp.import_repo(repo, dry_run=False)
        db = SessionLocal()
        try:
            recipes = db.scalars(select(models.Recipe)).all()
            assert len(recipes) == 2, f"食谱数应为 2，实际 {len(recipes)}"

            # 未知食材应被自动建表（咖喱块不在种子库）
            ings = {i.name for i in db.scalars(select(models.Ingredient)).all()}
            assert "咖喱块" in ings, "未知食材咖喱块应自动建表"
            assert "黄瓜" in ings, "黄瓜应存在"

            # 单人份折算：示例菜 一份够 2 人 -> 咖喱块 115/2 = 57.5
            rec = db.scalars(select(models.Recipe).where(models.Recipe.name == "示例菜")).first()
            items = {it.ingredient.name: it for it in rec.items}
            assert abs(items["咖喱块"].amount - 57.5) < 1e-6, \
                f"咖喱块单人份应为57.5，实际{items['咖喱块'].amount}"

            # 凉拌黄瓜 一份够 1 人 -> 不折算，黄瓜 200
            rec2 = db.scalars(select(models.Recipe).where(models.Recipe.name == "凉拌黄瓜")).first()
            items2 = {it.ingredient.name: it for it in rec2.items}
            assert items2["黄瓜"].amount == 200, \
                f"黄瓜应为200，实际{items2['黄瓜'].amount}"

            ri_count = sum(len(r.items) for r in recipes)
            assert ri_count > 0
        finally:
            db.close()

        # 幂等：重复导入不应翻倍
        imp.import_repo(repo, dry_run=False)
        db = SessionLocal()
        try:
            assert db.scalar(select(__import__("sqlalchemy").func.count(models.Recipe.id))) == 2, \
                "重复导入后食谱数应仍为 2"
            # 食材也不应翻倍
            ing_count = db.scalar(__import__("sqlalchemy").func.count(models.Ingredient.id))
            assert ing_count == len(ings), "重复导入后食材不应翻倍"
        finally:
            db.close()
        print("DB INTEGRATION OK: 2 食谱, 未知食材自动建表, 单人份折算正确, 幂等通过")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    test_import_and_idempotent()
