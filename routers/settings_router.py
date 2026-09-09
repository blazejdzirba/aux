from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from config import (
    get_omniroute_api_key, set_omniroute_api_key,
    get_optimizer_model_id, set_optimizer_model_id,
    get_omniroute_base, set_omniroute_base,
)
from services.catalog_client import fetch_catalog, clear_cache

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="templates")


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


def _ctx(saved: bool = False) -> dict:
    key = get_omniroute_api_key()
    base = get_omniroute_base()
    models = []
    catalog_error = ""
    try:
        models = fetch_catalog()
    except Exception as e:
        catalog_error = str(e)
    return {
        "active_page": "settings",
        "has_key": bool(key),
        "masked_key": _mask(key),
        "saved": saved,
        "models": models,
        "optimizer_model_id": get_optimizer_model_id(),
        "omniroute_base": base,
        "catalog_error": catalog_error,
    }


@router.get("", response_class=HTMLResponse)
async def settings_view(request: Request):
    return templates.TemplateResponse(request, "settings.html", _ctx())


@router.post("/omniroute-key", response_class=HTMLResponse)
async def save_key(request: Request, api_key: str = Form("")):
    set_omniroute_api_key(api_key)
    clear_cache()
    return templates.TemplateResponse(request, "settings.html", _ctx(saved=True))


@router.post("/omniroute-base", response_class=HTMLResponse)
async def save_base(request: Request, base_url: str = Form("")):
    set_omniroute_base(base_url)
    clear_cache()
    return templates.TemplateResponse(request, "settings.html", _ctx(saved=True))


@router.post("/optimizer-model", response_class=HTMLResponse)
async def save_optimizer_model(request: Request, model_id: str = Form("")):
    set_optimizer_model_id(model_id)
    return templates.TemplateResponse(request, "settings.html", _ctx(saved=True))
