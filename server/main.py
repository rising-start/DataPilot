from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api.tasks import router

app = FastAPI(title="DataPilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# 前端构建产物存在时挂载（web/ 构建后才有 web/dist）；用绝对路径避免工作目录影响
DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")
