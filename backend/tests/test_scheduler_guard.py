"""回归测试：fetch_today_prices 的「旧 mock 残留」守卫。

背景：旧镜像曾把今天的 mock 记录写入持久卷，导致新容器启动时
`if exists: return` 早退、真实抓取被跳过。修复后应先清当天 mock 再抓，
且仅当已有真实记录才跳过（幂等）。本测试防止该守卫逻辑回归。
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="sched_guard_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 't.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.services import scheduler  # noqa: E402

MOCK = "模拟数据(演示)"


class FakeRealSource:
    """模拟「政府指导价」真实源：对所有食材返回固定真实价。"""
    source_name = "政府指导价"
    last_sources: dict = {}
    last_specs: dict = {}

    def fetch(self, ingredients, day):
        return {ing.id: 9.99 for ing in ingredients}


def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def _run_with_fake():
    orig = scheduler.get_price_source
    scheduler.get_price_source = lambda: FakeRealSource()
    try:
        scheduler.fetch_today_prices()
    finally:
        scheduler.get_price_source = orig


def main():
    db = _reset_db()
    today = date.today()
    ing = models.Ingredient(name="测试菜", category="蔬菜", unit="g",
                            base_price=5.0)
    db.add(ing)
    db.commit()
    # 预置：今天已有旧 mock 记录（模拟旧镜像残留）
    db.add(models.PriceRecord(ingredient_id=ing.id, price=1.0, spec="500g",
                              date=today, source=MOCK))
    db.commit()

    # 第一次运行：应清掉 mock、写入真实价
    _run_with_fake()
    recs = db.scalars(select(models.PriceRecord)
                      .where(models.PriceRecord.date == today)).all()
    assert len(recs) == 1, f"应仅 1 条记录，实际 {len(recs)}"
    assert recs[0].source == "政府指导价", f"应被真实价替换，实际 {recs[0].source}"
    assert recs[0].price == 9.99, f"价格应为真实价，实际 {recs[0].price}"
    print("[OK] 旧 mock 被清除，真实价落库")

    # 第二次运行：已有真实记录，应幂等跳过、不重复写
    _run_with_fake()
    recs2 = db.scalars(select(models.PriceRecord)
                       .where(models.PriceRecord.date == today)).all()
    assert len(recs2) == 1, f"幂等：应仍仅 1 条，实际 {len(recs2)}"
    print("[OK] 再次运行幂等，无重复抓取/写入")

    db.close()
    print("\n✓ scheduler 守卫回归测试全部通过")


if __name__ == "__main__":
    main()
