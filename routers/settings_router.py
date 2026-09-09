from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from config import get_omniroute_api_key, set_omniroute_api_key

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="templates")


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


@router.get("", response_class=HTMLResponse)
async def settings_view(request: Request):
    key = get_omniroute_api_key()
    return templates.TemplateResponse(
        request, "settings.html",
        {"active_page": "settings", "has_key": bool(key), "masked_key": _mask(key), "saved": False},
    )


@router.post("/omniroute-key", response_class=HTMLResponse)
async def save_key(request: Request, api_key: str = Form("")):
    set_omniroute_api_key(api_key)
    key = get_omniroute_api_key()
    return templates.TemplateResponse(
        request, "settings.html",
        {"active_page": "settings", "has_key": bool(key), "masked_key": _mask(key), "saved": True},
    )
