from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..services.price_engine import CompositePriceSource, get_price_source
from ..services.pricing import parse_weight_g

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/latest")
def latest_prices(db: Session = Depends(get_db)):
    """每种食材的最新价格（含相对上一期涨跌幅）。

    返回全部食材：匹配到可靠价的 available=True 并带 source；
    政府价/电商均未匹配到的 available=False、source='暂无可靠价'，前端灰标展示。

    change_7d：本期(最新一条)相对上一期(窗口内倒数第二条)的涨跌幅，
    仅当窗口内≥2条记录时计算，否则为 None（前端显示『—』，不臆造 0%）。
    """
    today = date.today()
    window_start = today - timedelta(days=14)
    # 一次性取出窗口内全部价格记录，避免「每食材一次查询」的 N+1
    recs = db.scalars(
        select(models.PriceRecord)
        .where(models.PriceRecord.date >= window_start)
        .order_by(models.PriceRecord.date)).all()
    by_ing: dict[int, list] = {}
    for r in recs:
        by_ing.setdefault(r.ingredient_id, []).append(r)

    out = []
    for ing in db.scalars(select(models.Ingredient)).all():
        rows = by_ing.get(ing.id, [])
        if not rows:
            out.append({
                "ingredient_id": ing.id, "name": ing.name, "icon": ing.icon,
                "category": ing.category, "price": None, "spec": None,
                "date": None, "change_7d": None,
                "source": "暂无可靠价", "available": False, "source_url": None,
            })
            continue
        cur = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else None
        # 真正的「环比」：本期 vs 上一期；上一期为 0 或无数据时记为 None
        change = (cur.price - prev.price) / prev.price * 100 if (prev and prev.price) else None
        out.append({
            "ingredient_id": ing.id, "name": ing.name, "icon": ing.icon,
            "category": ing.category, "price": cur.price, "spec": cur.spec,
            "date": cur.date.isoformat(),
            "change_7d": round(change, 1) if change is not None else None,
            "source": cur.source, "available": True,
            "source_url": cur.source_url,
        })
    return out


@router.patch("/{ingredient_id}/normalize")
def normalize_price(ingredient_id: int, payload: schemas.PriceNormalizeIn,
                    db: Session = Depends(get_db)):
    """手动修正价格单位：用户提供克重描述（如 5kg/500g/1斤），
    系统解析克重后将价格归一化为『元/500克』并更新规格。
    仅对当天记录生效；无记录时 404。
    """
    ing = db.get(models.Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(404, "食材不存在")
    today = date.today()
    rec = db.scalars(
        select(models.PriceRecord)
        .where(models.PriceRecord.ingredient_id == ingredient_id,
               models.PriceRecord.date == today)
        .limit(1)).first()
    if not rec:
        raise HTTPException(404, "今天暂无价格记录")
    w = parse_weight_g(payload.raw_weight)
    if w is None:
        raise HTTPException(400, f"无法从『{payload.raw_weight}』解析克重，请用类似 5kg、500g、1斤 的写法")
    new_price = round(rec.price / w * 500, 2)
    old_price, old_spec = rec.price, rec.spec
    rec.price = new_price
    rec.spec = "元/500克"
    db.commit()
    return {
        "ok": True,
        "ingredient_id": ingredient_id,
        "old_price": old_price, "old_spec": old_spec,
        "new_price": new_price, "new_spec": "元/500克",
        "parsed_weight_g": w,
    }


@router.get("/source")
def price_source_info():
    """当前价格源组成，供前端透明展示。"""
    src = get_price_source()
    if isinstance(src, CompositePriceSource):
        return {
            "type": "composite",
            "sources": [s.source_name for s in src.sources],
            "note": "政府真实价优先，未匹配食材由电商平台兜底；均无价则灰标『暂无可靠价』",
        }
    return {"type": "single", "source": src.source_name}


@router.get("/trend/{ingredient_id}", response_model=schemas.PriceTrendOut)
def price_trend(ingredient_id: int, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
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
        # 与 /latest 保持一致：无数据时为『暂无可靠价』，而非误导性的『模拟数据』
        source=rows[-1].source if rows else "暂无可靠价")
