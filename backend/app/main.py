"""家庭智能膳食规划与进销存管理系统 — FastAPI 入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import UPLOAD_DIR
from .seed import seed_all
from .services.scheduler import start_scheduler
from .routers import (dashboard, ingredients, inventory, nutrition, planner,
                      prices, recipes, shopping)


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_all()          # 首次启动自动建表 + 种子数据
    start_scheduler()   # 每日菜价定时任务
    yield


app = FastAPI(title="家庭智能膳食规划与进销存管理系统", version="1.0.0",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])

for r in (prices, ingredients, recipes, nutrition, planner, inventory,
          shopping, dashboard):
    app.include_router(r.router)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}
