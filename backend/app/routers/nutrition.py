from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------- 营养目标模板 ----------
@router.get("/templates", response_model=list[schemas.NutritionTemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.scalars(select(models.NutritionTemplate)).all()


@router.post("/templates", response_model=schemas.NutritionTemplateOut)
def create_template(payload: schemas.NutritionTemplateIn, db: Session = Depends(get_db)):
    t = models.NutritionTemplate(**payload.model_dump())
    if t.is_active:
        for o in db.scalars(select(models.NutritionTemplate)):
            o.is_active = False
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.put("/templates/{tid}", response_model=schemas.NutritionTemplateOut)
def update_template(tid: int, payload: schemas.NutritionTemplateIn,
                    db: Session = Depends(get_db)):
    t = db.get(models.NutritionTemplate, tid)
    if not t:
        raise HTTPException(404, "模板不存在")
    if payload.is_active:
        for o in db.scalars(select(models.NutritionTemplate)):
            o.is_active = False
    for k, v in payload.model_dump().items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db)):
    t = db.get(models.NutritionTemplate, tid)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


# ---------- 每周天餐次配置 ----------
@router.get("/schedule", response_model=list[schemas.MealScheduleOut])
def get_schedule(db: Session = Depends(get_db)):
    return db.scalars(select(models.MealSchedule)
                      .order_by(models.MealSchedule.weekday)).all()


@router.put("/schedule", response_model=list[schemas.MealScheduleOut])
def update_schedule(payload: list[schemas.MealScheduleIn], db: Session = Depends(get_db)):
    """按周天批量更新餐次开关（支持周末只吃两顿等个性化组合）。"""
    for item in payload:
        row = db.scalars(select(models.MealSchedule)
                         .where(models.MealSchedule.weekday == item.weekday)).first()
        if row:
            row.breakfast, row.lunch, row.dinner = item.breakfast, item.lunch, item.dinner
        else:
            db.add(models.MealSchedule(**item.model_dump()))
    db.commit()
    return db.scalars(select(models.MealSchedule)
                      .order_by(models.MealSchedule.weekday)).all()


# ---------- 家庭设置 ----------
@router.get("/family", response_model=schemas.FamilySettingsOut)
def get_family(db: Session = Depends(get_db)):
    s = db.scalars(select(models.FamilySettings)).first()
    if not s:
        s = models.FamilySettings()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.put("/family", response_model=schemas.FamilySettingsOut)
def update_family(payload: schemas.FamilySettingsIn, db: Session = Depends(get_db)):
    s = db.scalars(select(models.FamilySettings)).first()
    for k, v in payload.model_dump().items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s
