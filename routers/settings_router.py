from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from config import (
    get_omniroute_api_key, set_omniroute_api_key,
    get_optimizer_model_id, set_optimizer_model_id,
)
from models import list_ai_models

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
    return {
        "active_page": "settings",
        "has_key": bool(key),
        "masked_key": _mask(key),
        "saved": saved,
        "models": list_ai_models(),
        "optimizer_model_id": get_optimizer_model_id(),
    }


@router.get("", response_class=HTMLResponse)
async def settings_view(request: Request):
    return templates.TemplateResponse(request, "settings.html", _ctx())


@router.post("/omniroute-key", response_class=HTMLResponse)
async def save_key(request: Request, api_key: str = Form("")):
    set_omniroute_api_key(api_key)
    return templates.TemplateResponse(request, "settings.html", _ctx(saved=True))


@router.post("/optimizer-model", response_class=HTMLResponse)
async def save_optimizer_model(request: Request, model_id: str = Form("")):
    set_optimizer_model_id(model_id)
    return templates.TemplateResponse(request, "settings.html", _ctx(saved=True))
