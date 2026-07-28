from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/latest")
def latest_prices(db: Session = Depends(get_db)):
    """每种食材的最新价格（含相对 7 天前涨跌幅）。"""
    today = date.today()
    out = []
    for ing in db.scalars(select(models.Ingredient)).all():
        rows = db.scalars(
            select(models.PriceRecord)
            .where(models.PriceRecord.ingredient_id == ing.id,
                   models.PriceRecord.date >= today - timedelta(days=8))
            .order_by(models.PriceRecord.date)).all()
        if not rows:
            continue
        cur, old = rows[-1], rows[0]
        change = (cur.price - old.price) / old.price * 100 if old.price else 0
        out.append({
            "ingredient_id": ing.id, "name": ing.name, "icon": ing.icon,
            "category": ing.category, "price": cur.price, "spec": cur.spec,
            "date": cur.date.isoformat(), "change_7d": round(change, 1),
            "source": cur.source,
        })
    return out


@router.get("/trend/{ingredient_id}", response_model=schemas.PriceTrendOut)
def price_trend(ingredient_id: int, days: int = 30, db: Session = Depends(get_db)):
    """价格趋势（周/月/季维度由 days 控制，前端图表支持横滑）。"""
    ing = db.get(models.Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(404, "食材不存在")
    rows = db.scalars(
        select(models.PriceRecord)
        .where(models.PriceRecord.ingredient_id == ingredient_id,
               models.PriceRecord.date >= date.today() - timedelta(days=days))
        .order_by(models.PriceRecord.date)).all()
    return schemas.PriceTrendOut(
        ingredient_id=ing.id, ingredient_name=ing.name,
        dates=[r.date.isoformat() for r in rows],
        prices=[r.price for r in rows],
        source=rows[-1].source if rows else "模拟数据(演示)")
