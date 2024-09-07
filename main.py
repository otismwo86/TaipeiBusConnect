# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from controller import router as main_router  # 從 controllers 導入路由

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(main_router)  # 包含控制器層的路由


