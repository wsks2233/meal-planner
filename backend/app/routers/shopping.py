from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas
from ..services.long_term import build_ics

router = APIRouter(prefix="/api/shopping", tags=["shopping"])


def _out(it: models.ShoppingItem) -> schemas.ShoppingItemOut:
    o = schemas.ShoppingItemOut.model_validate(it)
    o.ingredient_name = it.ingredient.name
    o.icon = it.ingredient.icon
    o.storage_method = it.ingredient.storage_method
    return o


@router.get("", response_model=list[schemas.ShoppingItemOut])
def list_items(only_pending: bool = False, db: Session = Depends(get_db)):
    stmt = (select(models.ShoppingItem)
            .options(selectinload(models.ShoppingItem.ingredient))
            .order_by(models.ShoppingItem.bought,
                      models.ShoppingItem.suggest_date,
                      models.ShoppingItem.batch_no))
    rows = db.scalars(stmt).all()
    if only_pending:
        rows = [r for r in rows if not r.bought]
    return [_out(r) for r in rows]


@router.post("/buy")
def mark_bought(payload: schemas.BuyIn, db: Session = Depends(get_db)):
    """一键勾选"已购买"/取消勾选。"""
    for iid in payload.item_ids:
        it = db.get(models.ShoppingItem, iid)
        if it:
            it.bought = payload.bought
    db.commit()
    return {"ok": True}


@router.post("/merge-pending")
def merge_pending(db: Session = Depends(get_db)):
    """把历史未购买项合并为一条新清单（同食材数量合并，旧记录清除）。"""
    rows = db.scalars(select(models.ShoppingItem)
                      .where(models.ShoppingItem.bought == False)).all()  # noqa: E712
    merged: dict[int, dict] = {}
    for r in rows:
        m = merged.setdefault(r.ingredient_id, {"qty": 0.0, "price": 0.0, "unit": r.unit})
        m["qty"] += r.need_qty
        m["price"] += r.est_price
        db.delete(r)
    for ing_id, m in merged.items():
        db.add(models.ShoppingItem(
            ingredient_id=ing_id, need_qty=m["qty"], unit=m["unit"],
            est_price=round(m["price"], 2), suggest_date=date.today()))
    db.commit()
    return {"ok": True, "merged": len(merged)}


@router.delete("/{item_id}")
def remove_item(item_id: int, db: Session = Depends(get_db)):
    it = db.get(models.ShoppingItem, item_id)
    if it:
        db.delete(it)
        db.commit()
    return {"ok": True}


@router.get("/calendar.ics")
def purchase_calendar(plan_id: int | None = None, db: Session = Depends(get_db)):
    """采购日历 ICS 导出：手机端下载后可添加到系统日历。"""
    stmt = select(models.ShoppingItem).where(models.ShoppingItem.bought == False)  # noqa: E712
    if plan_id:
        stmt = stmt.where(models.ShoppingItem.plan_id == plan_id)
    rows = db.scalars(stmt).all()
    items = [{"ingredient_id": r.ingredient_id, "need_qty": r.need_qty,
              "unit": r.unit, "suggest_date": r.suggest_date or date.today()}
             for r in rows]
    ics = build_ics(items, db)
    return Response(content=ics, media_type="text/calendar",
                    headers={"Content-Disposition":
                             "attachment; filename=purchase-calendar.ics"})
