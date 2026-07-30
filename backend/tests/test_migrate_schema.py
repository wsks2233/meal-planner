"""migrate_schema 迁移测试：去重 + 唯一索引幂等性。"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="migrate_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 't.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date  # noqa: E402

from sqlalchemy import select, text  # noqa: E402

from app.database import Base, engine, SessionLocal, migrate_schema  # noqa: E402
from app import models  # noqa: E402


def main():
    today = date.today()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    # 预置重复：同一 (食材, 日期, 来源) 两条
    db.add(models.PriceRecord(ingredient_id=1, price=1.0, spec="500g",
                              date=today, source="模拟数据(演示)"))
    db.add(models.PriceRecord(ingredient_id=1, price=2.0, spec="500g",
                              date=today, source="模拟数据(演示)"))
    db.add(models.PriceRecord(ingredient_id=1, price=3.0, spec="元/千克",
                              date=today, source="政府指导价"))  # 不同源，不冲突
    db.commit()
    db.close()

    migrate_schema()  # 第一次：去重 + 建索引
    migrate_schema()  # 第二次：应幂等，不报错

    db = SessionLocal()
    rows = db.scalars(select(models.PriceRecord)
                      .where(models.PriceRecord.date == today)).all()
    # (1,today,mock) 去重后留 1 条 + (1,today,真实) 1 条 = 2 条
    assert len(rows) == 2, f"去重后应 2 条，实际 {len(rows)}"
    srcs = sorted(r.source for r in rows)
    assert srcs == ["政府指导价", "模拟数据(演示)"], srcs
    print(f"[OK] 去重 + 唯一索引生效，剩余 {len(rows)} 条: {srcs}")

    # 验证唯一索引确实拦截重复插入
    db.add(models.PriceRecord(ingredient_id=1, price=9.9, spec="500g",
                              date=today, source="政府指导价"))
    try:
        db.commit()
        dup_ok = True
    except Exception:
        db.rollback()
        dup_ok = False
    assert not dup_ok, "唯一索引应拦截 (食材,日期,来源) 重复插入"
    print("[OK] 唯一索引拦截重复插入")
    db.close()
    print("\n✓ migrate_schema 迁移测试全部通过")


if __name__ == "__main__":
    main()
