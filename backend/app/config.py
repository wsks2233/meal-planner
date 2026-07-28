"""应用配置：通过环境变量切换 SQLite(开发) / PostgreSQL(生产)。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 开发默认 SQLite，Docker 中通过环境变量注入 postgres 连接串
# 例: postgresql+psycopg2://meal:meal@db:5432/meal
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'meal.db'}")

# 上传目录（用户食谱成品图）
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 临期判定阈值：剩余保质期 <= 该天数视为"临期"
EXPIRING_SOON_DAYS = int(os.getenv("EXPIRING_SOON_DAYS", "3"))

# 菜价历史回填天数（用于趋势图演示）
PRICE_BACKFILL_DAYS = int(os.getenv("PRICE_BACKFILL_DAYS", "90"))

# 推荐算法迭代次数（模拟退火简化版）
OPTIMIZER_ITERATIONS = int(os.getenv("OPTIMIZER_ITERATIONS", "400"))
