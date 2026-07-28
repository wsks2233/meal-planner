import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import UPLOAD_DIR
from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _detail(r: models.Recipe) -> schemas.RecipeDetailOut:
    out = schemas.RecipeDetailOut.model_validate(r)
    out.items = [schemas.RecipeItemOut(
        ingredient_id=it.ingredient_id, amount=it.amount, unit=it.unit,
        ingredient_name=it.ingredient.name, icon=it.ingredient.icon)
        for it in r.items]
    return out


@router.get("", response_model=list[schemas.RecipeOut])
def list_recipes(category: str | None = None, meal_type: str | None = None,
                 q: str | None = None, max_minutes: int | None = None,
                 db: Session = Depends(get_db)):
    stmt = select(models.Recipe)
    if category:
        stmt = stmt.where(models.Recipe.category == category)
    if q:
        stmt = stmt.where(models.Recipe.name.contains(q))
    if max_minutes:  # 烹饪时长过滤（如工作日只做快手菜）
        stmt = stmt.where(models.Recipe.cook_minutes <= max_minutes)
    rows = db.scalars(stmt.order_by(models.Recipe.id)).all()
    if meal_type:
        rows = [r for r in rows if meal_type in (r.meal_types or [])]
    return rows


@router.get("/{recipe_id}", response_model=schemas.RecipeDetailOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    r = db.scalars(select(models.Recipe).where(models.Recipe.id == recipe_id)
                   .options(selectinload(models.Recipe.items)
                            .selectinload(models.RecipeIngredient.ingredient))).first()
    if not r:
        raise HTTPException(404, "食谱不存在")
    return _detail(r)


@router.post("", response_model=schemas.RecipeDetailOut)
def create_recipe(payload: schemas.RecipeIn, db: Session = Depends(get_db)):
    """用户自定义食谱（可带烹饪时长/备注，图片单独上传）。"""
    if db.scalars(select(models.Recipe).where(models.Recipe.name == payload.name)).first():
        raise HTTPException(400, "同名食谱已存在")
    r = models.Recipe(**payload.model_dump(exclude={"items"}), is_builtin=False)
    db.add(r)
    db.flush()
    for it in payload.items:
        db.add(models.RecipeIngredient(recipe_id=r.id, **it.model_dump()))
    db.commit()
    db.refresh(r)
    return _detail(r)


@router.post("/{recipe_id}/image")
def upload_image(recipe_id: int, file: UploadFile, db: Session = Depends(get_db)):
    """上传成品图。"""
    r = db.get(models.Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "食谱不存在")
    ext = (file.filename or "x.jpg").rsplit(".", 1)[-1].lower()
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        raise HTTPException(400, "仅支持 jpg/png/webp")
    fname = f"{uuid.uuid4().hex}.{ext}"
    with open(UPLOAD_DIR / fname, "wb") as f:
        shutil.copyfileobj(file.file, f)
    r.image_url = f"/uploads/{fname}"
    db.commit()
    return {"image_url": r.image_url}


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    r = db.get(models.Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "食谱不存在")
    if r.is_builtin:
        raise HTTPException(400, "内置食谱不可删除")
    db.delete(r)
    db.commit()
    return {"ok": True}
