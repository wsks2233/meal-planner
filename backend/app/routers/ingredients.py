from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


@router.get("", response_model=list[schemas.IngredientOut])
def list_ingredients(category: str | None = None, q: str | None = None,
                     db: Session = Depends(get_db)):
    stmt = select(models.Ingredient)
    if category:
        stmt = stmt.where(models.Ingredient.category == category)
    if q:
        stmt = stmt.where(models.Ingredient.name.contains(q))
    return db.scalars(stmt.order_by(models.Ingredient.category)).all()


@router.get("/barcode/{code}", response_model=schemas.IngredientOut)
def by_barcode(code: str, db: Session = Depends(get_db)):
    """模拟扫码：按条形码查食材（演示条码 69100000000 起）。"""
    ing = db.scalars(select(models.Ingredient)
                     .where(models.Ingredient.barcode == code)).first()
    if not ing:
        raise HTTPException(404, "未找到该条码对应的食材")
    return ing
