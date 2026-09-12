"""Radar free LLM: snapshot ofert + diff + nowości (strona + API).

- GET  /radar              -> strona
- POST /radar/api/refresh  -> sprawdź teraz (omija strażnik dzienny)
- POST /radar/api/seen     -> oznacz wszystkie nowości jako przeczytane
- GET  /radar/api/unseen   -> {count} (badge w nawigacji)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import radar

router = APIRouter(tags=["radar"])
templates = Jinja2Templates(directory="templates")


@router.get("/radar", response_class=HTMLResponse)
async def radar_view(request: Request):
    try:
        status = radar.get_status()
        news = radar.list_news()
        providers = radar.list_providers()
        models = radar.list_models()
    except Exception:
        status = {"last_fetch_at": "", "last_status": "", "providers": 0,
                  "models": 0, "unseen": 0}
        news, providers, models = [], [], []
    return templates.TemplateResponse(
        request, "radar.html",
        {"request": request, "active_page": "radar", "status": status,
         "news": news, "providers": providers, "models": models},
    )


@router.post("/radar/api/refresh")
async def api_refresh():
    try:
        out = radar.refresh(force=True)
    except Exception as exc:
        return JSONResponse({"status": "error", "error": str(exc)})
    return JSONResponse({"status": "ok", "result": out})


@router.post("/radar/api/seen")
async def api_seen():
    try:
        n = radar.mark_all_seen()
    except Exception as exc:
        return JSONResponse({"status": "error", "error": str(exc)})
    return JSONResponse({"status": "ok", "marked": n})


@router.get("/radar/api/unseen")
async def api_unseen():
    try:
        return JSONResponse({"count": radar.get_unseen_count()})
    except Exception:
        return JSONResponse({"count": 0})
