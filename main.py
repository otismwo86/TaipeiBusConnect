from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from controller import router as main_router

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(main_router)


