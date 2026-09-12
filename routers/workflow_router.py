"""Workflow: statyczne ściągi procesów — strona + JSON API (CRUD procesów i kroków).

- GET    /workflows                      -> strona
- GET    /workflows/api                  -> wszystko (procesy + kroki)
- POST   /workflows/api                  -> nowy proces {name, description}
- PUT    /workflows/api/{wid}            -> edycja procesu
- DELETE /workflows/api/{wid}            -> usuń proces (+ kroki)
- POST   /workflows/api/{wid}/steps      -> nowy krok
- PUT    /workflows/api/steps/{sid}      -> edycja kroku
- DELETE /workflows/api/steps/{sid}      -> usuń krok
- POST   /workflows/api/steps/{sid}/move -> przesuń {dir: up|down}
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import workflows

router = APIRouter(tags=["workflow"])
templates = Jinja2Templates(directory="templates")


def _err(msg):
    return JSONResponse({"status": "error", "error": msg})


@router.get("/workflows", response_class=HTMLResponse)
async def workflows_view(request: Request):
    try:
        data = workflows.list_all()
    except Exception:
        data = []
    return templates.TemplateResponse(
        request, "workflows.html",
        {"request": request, "active_page": "workflow", "workflows": data},
    )


@router.get("/workflows/api")
async def api_list():
    try:
        return JSONResponse({"status": "ok", "workflows": workflows.list_all()})
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")


@router.post("/workflows/api")
async def api_create(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    try:
        wid = workflows.create_workflow(body.get("name"), body.get("description"))
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    return JSONResponse({"status": "ok", "id": wid})


@router.put("/workflows/api/{wid}")
async def api_update(wid: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    try:
        ok = workflows.update_workflow(wid, body.get("name"), body.get("description"))
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    if not ok:
        return _err("Nie ma takiego procesu.")
    return JSONResponse({"status": "ok"})


@router.delete("/workflows/api/{wid}")
async def api_delete(wid: int):
    try:
        ok = workflows.delete_workflow(wid)
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    if not ok:
        return _err("Nie ma takiego procesu.")
    return JSONResponse({"status": "ok"})


def _step_fields(body):
    return (body.get("title"), body.get("instructions"), body.get("prompt"),
            body.get("template_name"), body.get("template_body"))


@router.post("/workflows/api/{wid}/steps")
async def api_step_add(wid: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    try:
        sid = workflows.add_step(wid, *_step_fields(body))
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    return JSONResponse({"status": "ok", "id": sid})


@router.put("/workflows/api/steps/{sid}")
async def api_step_update(sid: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    try:
        ok = workflows.update_step(sid, *_step_fields(body))
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    if not ok:
        return _err("Nie ma takiego kroku.")
    return JSONResponse({"status": "ok"})


@router.delete("/workflows/api/steps/{sid}")
async def api_step_delete(sid: int):
    try:
        ok = workflows.delete_step(sid)
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    if not ok:
        return _err("Nie ma takiego kroku.")
    return JSONResponse({"status": "ok"})


@router.post("/workflows/api/steps/{sid}/move")
async def api_step_move(sid: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    if body.get("dir") not in ("up", "down"):
        return _err("Nieznany kierunek.")
    try:
        workflows.move_step(sid, body.get("dir"))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    return JSONResponse({"status": "ok"})
