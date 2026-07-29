FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 电商兜底源（慢慢买）依赖 Playwright 无头 Chromium，需安装浏览器二进制
# --with-deps 会一并安装系统级依赖（Debian/Ubuntu 系）
RUN playwright install --with-deps chromium

# 再拷贝应用代码
COPY app/ ./app/

# 拷贝一次性数据导入脚本（HowToCook 菜谱导入等），便于 docker compose exec 执行
COPY scripts/ ./scripts/

# 持久化数据目录（数据库 + 上传图片），由 docker-compose 挂载卷
RUN mkdir -p /data/uploads

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
