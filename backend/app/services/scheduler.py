"""APScheduler 定时任务：每日抓取/生成菜价。

合规说明：真实抓取场景应遵守目标站点 robots.txt 与访问频率限制，
本调度器默认每日仅执行一次，且 price_engine 内置缓存与重试机制。
"""
import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from ..database import SessionLocal
from .. import models
from .price_engine import get_price_source

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def fetch_today_prices():
    db = SessionLocal()
    try:
        today = date.today()
        exists = db.scalars(select(models.PriceRecord)
                            .where(models.PriceRecord.date == today).limit(1)).first()
        if exists:
            return
        src = get_price_source()
        ingredients = db.scalars(select(models.Ingredient)).all()
        prices = src.fetch_cached(ingredients, today)
        for ing in ingredients:
            db.add(models.PriceRecord(
                ingredient_id=ing.id, price=prices[ing.id],
                spec=f"500{ing.unit}", date=today, source=src.source_name))
        db.commit()
        log.info("Fetched %d prices for %s", len(prices), today)
    except Exception:  # noqa: BLE001
        log.exception("price fetch failed")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每日 00:10 生成当日菜价（真实源场景避开整点高峰）
    _scheduler.add_job(fetch_today_prices, "cron", hour=0, minute=10,
                       id="daily_prices", replace_existing=True)
    _scheduler.start()
    fetch_today_prices()  # 启动时补齐当日
    return _scheduler
