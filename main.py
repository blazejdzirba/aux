import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from database import init_db
import finders


def _radar_startup_check():
    """Auto-check Radaru raz dziennie, w tle (nie blokuje startu)."""
    try:
        import radar
        radar.refresh_if_stale()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    finders.ensure_db()
    threading.Thread(target=_radar_startup_check, daemon=True).start()
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

from routers.vault_router import router as vault_router
app.include_router(vault_router)

from routers.resources_router import router as resources_router
app.include_router(resources_router)

from routers.prompts_router import router as prompts_router
app.include_router(prompts_router)

from routers.projects_router import router as projects_router
app.include_router(projects_router)

from routers.translator_router import router as translator_router
app.include_router(translator_router)

from routers.converter_router import router as converter_router
app.include_router(converter_router)

from routers.voice_router import router as voice_router
app.include_router(voice_router)

from routers.finder_router import router as finder_router
app.include_router(finder_router)

from routers.workflow_router import router as workflow_router
app.include_router(workflow_router)

from routers.radar_router import router as radar_router
app.include_router(radar_router)


@app.get("/")
async def root():
    return RedirectResponse("/models", status_code=307)


@app.get("/health")
async def health():
    return {"status": "ok"}
