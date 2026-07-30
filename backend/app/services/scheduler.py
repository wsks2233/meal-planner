"""APScheduler 定时任务：每日抓取/生成菜价。

合规说明：真实抓取场景应遵守目标站点 robots.txt 与访问频率限制，
本调度器默认每周仅执行一次，且 price_engine 内置缓存与重试机制。
"""
import logging
import threading
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete, select

from ..database import SessionLocal
from .. import models
from .price_engine import get_price_source

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None

_MOCK_SOURCE = "模拟数据(演示)"


def fetch_today_prices():
    db = SessionLocal()
    try:
        today = date.today()
        # 清理当天残留的「模拟数据(演示)」记录（旧镜像/历史 mock 写入），
        # 避免遮住本次真实抓取；已存在的真实记录保留（幂等：重启不重复抓）。
        db.execute(delete(models.PriceRecord)
                   .where(models.PriceRecord.date == today,
                          models.PriceRecord.source == _MOCK_SOURCE))
        db.commit()
        has_real = db.scalars(
            select(models.PriceRecord)
            .where(models.PriceRecord.date == today,
                   models.PriceRecord.source != _MOCK_SOURCE)
            .limit(1)).first()
        if has_real:
            return
        src = get_price_source()
        ingredients = db.scalars(select(models.Ingredient)).all()
        # 直接调 fetch（非 fetch_cached），以便读取复合源的逐食材来源/规格
        prices = src.fetch(ingredients, today) or {}
        sources = getattr(src, "last_sources", {}) or {}
        specs = getattr(src, "last_specs", {}) or {}
        for ing in ingredients:
            pid = ing.id
            if pid not in prices:
                # 政府价/电商均未匹配：不写入模拟价，留待前端灰标「暂无可靠价」
                continue
            db.add(models.PriceRecord(
                ingredient_id=pid, price=prices[pid],
                spec=specs.get(pid, "元/500克"),
                date=today, source=sources.get(pid, src.source_name)))
        db.commit()
        log.info("Fetched %d prices for %s (of %d ingredients)", len(prices), today, len(ingredients))
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
    # 每周一 00:10 抓取（政府价每周日发布一期，周一落库；避开整点高峰）
    _scheduler.add_job(fetch_today_prices, "cron", day_of_week="mon", hour=0, minute=10,
                       id="weekly_prices", replace_existing=True)
    _scheduler.start()
    # 后台线程执行首次抓取：避免阻塞 uvicorn 启动（真实源含浏览器渲染，可能耗时数十秒）
    threading.Thread(target=fetch_today_prices, daemon=True).start()
    return _scheduler
