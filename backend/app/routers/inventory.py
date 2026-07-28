from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import EXPIRING_SOON_DAYS
from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def batch_out(b: models.InventoryBatch) -> schemas.BatchOut:
    o = schemas.BatchOut.model_validate(b)
    o.ingredient_name = b.ingredient.name
    o.icon = b.ingredient.icon
    days = (b.expire_date - date.today()).days
    o.days_left = days
    o.status = ("过期" if days < 0
                else "临期" if days <= EXPIRING_SOON_DAYS else "新鲜")
    return o


@router.get("", response_model=list[schemas.BatchOut])
def list_batches(status: str | None = None, storage: str | None = None,
                 db: Session = Depends(get_db)):
    """库存视图：按状态（新鲜/临期/过期）与保存方式筛选。"""
    rows = db.scalars(
        select(models.InventoryBatch)
        .where(models.InventoryBatch.discarded == False,  # noqa: E712
               models.InventoryBatch.remaining_qty > 0)
        .options(selectinload(models.InventoryBatch.ingredient))
        .order_by(models.InventoryBatch.expire_date)).all()
    out = [batch_out(b) for b in rows]
    if status:
        out = [o for o in out if o.status == status]
    if storage:
        out = [o for o in out if o.storage_method == storage]
    return out


@router.post("", response_model=schemas.BatchOut)
def purchase_in(payload: schemas.BatchIn, db: Session = Depends(get_db)):
    """"进"：采购入库。未填保质期/保存方式时按食材默认值自动规划。"""
    ing = db.get(models.Ingredient, payload.ingredient_id)
    if not ing:
        raise HTTPException(404, "食材不存在")
    expire = payload.expire_date or (
        payload.purchase_date + timedelta(days=ing.default_shelf_life_days))
    b = models.InventoryBatch(
        ingredient_id=ing.id, qty=payload.qty, remaining_qty=payload.qty,
        unit=payload.unit or ing.unit, unit_price=payload.unit_price,
        purchase_date=payload.purchase_date, expire_date=expire,
        storage_method=payload.storage_method or ing.storage_method,
        location=payload.location)
    db.add(b)
    db.commit()
    db.refresh(b)
    return batch_out(b)


@router.post("/consume")
def consume(payload: schemas.ConsumeIn, db: Session = Depends(get_db)):
    """"销"：手动记录消耗。"""
    b = db.get(models.InventoryBatch, payload.batch_id)
    if not b:
        raise HTTPException(404, "批次不存在")
    take = min(payload.qty, b.remaining_qty)
    b.remaining_qty -= take
    db.add(models.ConsumptionLog(batch_id=b.id, qty=take, date=date.today(),
                                 reason=payload.reason))
    db.commit()
    return {"ok": True, "consumed": take, "remaining": b.remaining_qty}


@router.post("/{batch_id}/discard")
def discard(batch_id: int, db: Session = Depends(get_db)):
    """标记已丢弃（过期废弃）。"""
    b = db.get(models.InventoryBatch, batch_id)
    if not b:
        raise HTTPException(404, "批次不存在")
    db.add(models.ConsumptionLog(batch_id=b.id, qty=b.remaining_qty,
                                 date=date.today(), reason="discard"))
    b.discarded = True
    b.remaining_qty = 0
    db.commit()
    return {"ok": True}


@router.post("/{batch_id}/to-shopping")
def add_to_shopping(batch_id: int, db: Session = Depends(get_db)):
    """一键把某库存食材加入购物清单（按原入库量补货）。"""
    b = db.get(models.InventoryBatch, batch_id)
    if not b:
        raise HTTPException(404, "批次不存在")
    db.add(models.ShoppingItem(
        ingredient_id=b.ingredient_id, need_qty=b.qty, unit=b.unit,
        est_price=round(b.qty / 500 * (b.unit_price or 5), 2)))
    db.commit()
    return {"ok": True}
