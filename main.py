from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="AUX", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

from routers.models_router import router as models_router
app.include_router(models_router)

from routers.playground_router import router as playground_router
app.include_router(playground_router)

from routers.documents_router import router as documents_router
app.include_router(documents_router)

from routers.settings_router import router as settings_router
app.include_router(settings_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
