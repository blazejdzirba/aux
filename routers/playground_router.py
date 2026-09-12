from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from services.omniroute_client import run_chat
from services.catalog_client import fetch_catalog
from database import get_db_connection
from models import list_ai_models

import services.prompt_optimizer as po

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DEFAULT_OPTIMIZER_MODEL = "auto/best-free"


@router.get("/playground", response_class=HTMLResponse)
async def playground_view(request: Request, model: str = ""):
    try:
        models = fetch_catalog()
    except Exception:
        models = []
    selected = (model or "").strip()
    # Model spoza katalogu (np. z 'W użyciu') — dopisz na początek listy,
    # żeby select miał co pokazać jako wybraną opcję.
    if selected and all(m.get("model_id") != selected for m in models):
        if "/" in selected:
            prefix, _, name = selected.partition("/")
        else:
            prefix, name = "inne", selected
        models = [{
            "model_id": selected,
            "provider_prefix": prefix.upper(),
            "model_name": name,
            "is_free": False,
        }] + models
    return templates.TemplateResponse(
        request, "playground.html",
        {"models": models, "active_page": "playground", "selected_model": selected},
    )


# ------------------------------------------------------------
# Optymalizator — widok
# ------------------------------------------------------------
@router.get("/optimizer", response_class=HTMLResponse)
async def optimizer_view(request: Request):
    snippets = _list_snippets()
    settings = {
        "model": po.get_setting(po.SETTING_MODEL) or "",
        "system_prompt": po.get_setting(po.SETTING_SYSTEM_PROMPT) or "",
    }
    try:
        models = list_ai_models()
    except Exception:
        models = []
    return templates.TemplateResponse(
        request, "optimizer.html",
        {
            "active_page": "optimizer",
            "snippets": snippets,
            "settings": settings,
            "models": models,
            "default_model": DEFAULT_OPTIMIZER_MODEL,
            "default_system_prompt": po.SYSTEM_PROMPT_BASE,
        },
    )


# Stare adresy optymalizatora — przekierowania na nową lokalizację.
@router.get("/prompt-optimizer")
async def optimizer_redirect_old():
    return RedirectResponse(url="/optimizer", status_code=302)


@router.get("/playground/optimizer")
async def optimizer_redirect_sub():
    return RedirectResponse(url="/optimizer", status_code=302)


# ------------------------------------------------------------
# Optymalizator — endpointy JSON
# ------------------------------------------------------------
def _selected_snippets(payload) -> list[dict]:
    ids = payload.get("snippet_ids") or []
    if not ids:
        return []
    all_snippets = {s["id"]: s for s in _list_snippets()}
    return [all_snippets[i] for i in ids if i in all_snippets]


def _optimizer_kwargs(payload: dict) -> dict:
    return {
        "model": payload.get("model") or None,
        "system_prompt": payload.get("system_prompt") or None,
        "snippets": _selected_snippets(payload),
    }


@router.post("/prompt-optimizer/optimize")
async def prompt_optimizer_optimize(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "text": "", "error": "Nieprawidłowy JSON"})
    prompt = (payload.get("prompt") or "").strip()
    mode = payload.get("mode") or "standard"
    if not prompt:
        return JSONResponse({"status": "error", "text": "", "error": "Brak treści promptu."})
    kw = _optimizer_kwargs(payload)
    try:
        if mode == "systemowy":
            text = po.create_system_prompt(prompt, **kw)
        elif mode == "mega":
            questions = (payload.get("questions") or "").strip()
            answers = (payload.get("answers") or "").strip()
            text = po.optimize_prompt_mega(prompt, questions, answers, **kw)
        else:
            text = po.optimize_prompt(prompt, **kw)
    except Exception as e:
        return JSONResponse({"status": "error", "text": "", "error": str(e)})
    return JSONResponse({"status": "ok", "text": text, "error": ""})


@router.post("/prompt-optimizer/questions")
async def prompt_optimizer_questions(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "text": "", "error": "Nieprawidłowy JSON"})
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"status": "error", "text": "", "error": "Brak treści promptu."})
    try:
        text = po.generate_questions(prompt, model=payload.get("model") or None)
    except Exception as e:
        return JSONResponse({"status": "error", "text": "", "error": str(e)})
    return JSONResponse({"status": "ok", "text": text, "error": ""})


@router.post("/prompt-optimizer/translate")
async def prompt_optimizer_translate(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "text": "", "error": "Nieprawidłowy JSON"})
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"status": "error", "text": "", "error": "Brak tekstu do tłumaczenia."})
    try:
        translated = po.translate_prompt(text, model=payload.get("model") or None)
    except Exception as e:
        return JSONResponse({"status": "error", "text": "", "error": str(e)})
    return JSONResponse({"status": "ok", "text": translated, "error": ""})


# ------------------------------------------------------------
# Optymalizator — ustawienia (model + customowy prompt systemowy)
# ------------------------------------------------------------
@router.get("/prompt-optimizer/settings")
async def prompt_optimizer_settings_get():
    return JSONResponse({
        "model": po.get_setting(po.SETTING_MODEL) or "",
        "system_prompt": po.get_setting(po.SETTING_SYSTEM_PROMPT) or "",
    })


@router.post("/prompt-optimizer/settings")
async def prompt_optimizer_settings_post(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "error": "Nieprawidłowy JSON"})
    if "model" in payload:
        po.set_setting(po.SETTING_MODEL, (payload.get("model") or "").strip())
    if "system_prompt" in payload:
        po.set_setting(po.SETTING_SYSTEM_PROMPT, payload.get("system_prompt") or "")
    return JSONResponse({"status": "ok", "error": ""})


# ------------------------------------------------------------
# Optymalizator — biblioteka fragmentów (snippets)
# ------------------------------------------------------------
def _list_snippets() -> list[dict]:
    try:
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT id, title, text, created_at FROM optimizer_snippets ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@router.get("/prompt-optimizer/snippets")
async def prompt_optimizer_snippets_list():
    return JSONResponse({"status": "ok", "snippets": _list_snippets()})


@router.post("/prompt-optimizer/snippets")
async def prompt_optimizer_snippets_create(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "error": "Nieprawidłowy JSON"})
    title = (payload.get("title") or "").strip()
    text = (payload.get("text") or "").strip()
    if not title or not text:
        return JSONResponse({"status": "error", "error": "Fragment wymaga tytułu i treści."})
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO optimizer_snippets (title, text) VALUES (?, ?)", (title, text)
    )
    conn.commit()
    conn.close()
    return JSONResponse({"status": "ok", "snippets": _list_snippets()})


@router.put("/prompt-optimizer/snippets/{snippet_id}")
async def prompt_optimizer_snippets_update(snippet_id: int, request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "error": "Nieprawidłowy JSON"})
    title = (payload.get("title") or "").strip()
    text = (payload.get("text") or "").strip()
    if not title or not text:
        return JSONResponse({"status": "error", "error": "Fragment wymaga tytułu i treści."})
    conn = get_db_connection()
    cur = conn.execute(
        "UPDATE optimizer_snippets SET title = ?, text = ? WHERE id = ?",
        (title, text, snippet_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return JSONResponse({"status": "error", "error": "Nie znaleziono fragmentu."})
    return JSONResponse({"status": "ok", "snippets": _list_snippets()})


@router.delete("/prompt-optimizer/snippets/{snippet_id}")
async def prompt_optimizer_snippets_delete(snippet_id: int):
    conn = get_db_connection()
    cur = conn.execute("DELETE FROM optimizer_snippets WHERE id = ?", (snippet_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return JSONResponse({"status": "error", "error": "Nie znaleziono fragmentu."})
    return JSONResponse({"status": "ok", "snippets": _list_snippets()})


# ------------------------------------------------------------
# Playground — czat
# ------------------------------------------------------------
@router.post("/playground/chat")
async def playground_chat(request: Request):
    """Czat Playground: przyjmuje JSON {model_id, messages: [{role, content}]} i zwraca odpowiedź modelu."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "text": "", "latency_ms": None, "error": "Nieprawidłowy JSON"})
    model_id = body.get("model_id", "")
    messages = body.get("messages", [])
    if not model_id or not messages:
        return JSONResponse({"status": "error", "text": "", "latency_ms": None, "error": "Brak model_id lub messages"})
    try:
        result = run_chat(model_id, messages)
    except Exception as e:
        result = {"status": "error", "text": "", "latency_ms": None, "error": str(e)}
    return JSONResponse(result)
