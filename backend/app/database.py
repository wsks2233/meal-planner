from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema():
    """轻量幂等迁移：建表 + price_records 唯一索引（先去重再建）。

    启动时调用一次。用原生 SQL 而非模型 __table_args__，以便对既有
    SQLite 卷 / Postgres 都生效（create_all 不会为已存在的表补约束）。
    唯一索引固化「同一食材同日同源仅一条」，防止旧 mock 残留或重复写入。
    """
    from sqlalchemy import text
    from . import models  # noqa: F401  确保模型已注册到 metadata

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # 1) 去重：同一 (ingredient_id, date, source) 只保留 id 最大的一条
        conn.execute(text(
            "DELETE FROM price_records WHERE id NOT IN ("
            "  SELECT MAX(id) FROM price_records"
            "  GROUP BY ingredient_id, date, source)"))
        # 2) 唯一索引（幂等）
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_price_records_iid_date_src"
            " ON price_records (ingredient_id, date, source)"))
    # 3) 新增列（幂等，单独事务避免回滚影响已有约束）
    for col_sql in [
        "ALTER TABLE price_records ADD COLUMN source_url VARCHAR(1024)",
        "ALTER TABLE meal_schedule ADD COLUMN lunch_courses INTEGER DEFAULT 2",
        "ALTER TABLE meal_schedule ADD COLUMN dinner_courses INTEGER DEFAULT 3",
        "ALTER TABLE family_settings ADD COLUMN staple_type VARCHAR(20) DEFAULT '米饭'",
        "ALTER TABLE family_settings ADD COLUMN staple_per_person_g INTEGER DEFAULT 150",
        "ALTER TABLE recipes ADD COLUMN prep_ahead_hours INTEGER DEFAULT 0",
    ]:
        try:
            with engine.begin() as conn2:
                conn2.execute(text(col_sql))
        except Exception:  # noqa: BLE001
            pass
