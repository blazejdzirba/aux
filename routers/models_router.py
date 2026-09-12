import json
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from models import (
    list_ai_models, get_model, delete_model, upsert_model, used_count,
    group_models_by_prefix, update_model_notes, get_provider_by_slug,
    set_favorite, list_favorite_models, favorite_count,
    update_model_status, fmt_context, backfill_context_from_catalog,
)
from catalog import list_used_model_ids, list_ignored_model_ids, ignore_models
from services.model_monitor import check_single_model
from services.batch_tester import start_catalog_batch, start_used_batch, get_job
from services.catalog_client import fetch_catalog, group_by_provider
from services.omniroute_client import run_prompt

router = APIRouter(prefix="/models", tags=["models"])
templates = Jinja2Templates(directory="templates")
templates.env.filters["ctx"] = fmt_context


@router.get("", response_class=HTMLResponse)
async def models_page(request: Request):
    # Lista providerów do statycznego paska akcji (katalog jest cache'owany).
    try:
        providers_all = sorted({it["provider_prefix"] for it in fetch_catalog()})
    except Exception:
        providers_all = []
    return templates.TemplateResponse(
        request, "models.html",
        {"active_page": "models", "used_count": used_count(), "fav_count": favorite_count(), "providers_all": providers_all},
    )


# ---------- Tab: Testowanie (katalog) ----------
def _catalog_context(query: str, provider: str, free: str, auto_add: str, ephemeral: dict | None = None) -> dict:
    provider_row = get_provider_by_slug("omniroute")
    try:
        items = fetch_catalog()
        error = None
    except Exception as e:
        items, error = [], str(e)

    used_ids = list_used_model_ids(provider_row["id"]) if provider_row else set()
    ignored_ids = list_ignored_model_ids()

    hidden_count = 0
    visible = []
    for it in items:
        if it["model_id"] in used_ids or it["model_id"] in ignored_ids:
            hidden_count += 1
        else:
            visible.append(it)

    providers_all = sorted({it["provider_prefix"] for it in items})

    if query:
        q = query.lower()
        visible = [it for it in visible if q in it["model_id"].lower()]
    if provider:
        visible = [it for it in visible if it["provider_prefix"] == provider]
    if free == "1":
        visible = [it for it in visible if it["is_free"]]

    return {
        "groups": group_by_provider(visible),
        "total": len(items),
        "hidden_count": hidden_count,
        "providers_all": providers_all,
        "query": query,
        "provider": provider,
        "free": free == "1",
        "auto_add": auto_add == "1",
        "error": error,
        "ephemeral": ephemeral or {},
    }


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_tab(request: Request, query: str = "", provider: str = "", free: str = "", auto_add: str = "1"):
    ctx = _catalog_context(query, provider, free, auto_add)
    return templates.TemplateResponse(request, "partials/catalog_results.html", ctx)


@router.post("/catalog/test", response_class=HTMLResponse)
async def catalog_test(
    request: Request,
    selected: list[str] = Form(default=[]),
    auto_add: str = Form("0"),
    query: str = Form(""),
    provider: str = Form(""),
    free: str = Form(""),
):
    if not selected:
        ctx = _catalog_context(query, provider, free, auto_add)
        return templates.TemplateResponse(request, "partials/catalog_results.html", ctx)

    # Testy w tle (wątki) + panel postępu z pollingiem — UI zostaje responsywne,
    # wyniki dopisują się na bieżąco (jak w starym projekcie).
    job_id = start_catalog_batch(selected, auto_add=(auto_add == "1"))
    job = get_job(job_id)
    return templates.TemplateResponse(request, "partials/batch_status.html", {"job": job})


@router.get("/batch/{job_id}/status", response_class=HTMLResponse)
async def batch_status(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        return HTMLResponse('<p class="muted">Job nie istnieje (serwer mógł się zrestartować).</p>')
    return templates.TemplateResponse(request, "partials/batch_status.html", {"job": job})


@router.post("/catalog/hide", response_class=HTMLResponse)
async def catalog_hide(
    request: Request,
    selected: list[str] = Form(default=[]),
    query: str = Form(""),
    provider: str = Form(""),
    free: str = Form(""),
    auto_add: str = Form("1"),
):
    ignore_models(selected)
    ctx = _catalog_context(query, provider, free, auto_add)
    return templates.TemplateResponse(request, "partials/catalog_results.html", ctx)


# ---------- Tab: W użyciu ----------
@router.get("/used", response_class=HTMLResponse)
async def used_tab(request: Request, query: str = "", free: str = "", sort: str = "name"):
    # Jednorazowe uzupełnienie kontekstu dla modeli dodanych przed tą zmianą
    # (katalog jest cache'owany 5 min, więc to tanie).
    try:
        backfill_context_from_catalog(fetch_catalog())
    except Exception:
        pass
    models = list_ai_models(query=query or None, free_only=(free == "1"), sort=sort)
    groups = group_models_by_prefix(models)
    return templates.TemplateResponse(
        request, "partials/used_results.html",
        {"groups": groups, "total": len(models), "query": query, "free": free == "1", "sort": sort},
    )


# ---------- Tab: Ulubione ----------
@router.get("/favorites", response_class=HTMLResponse)
async def favorites_tab(request: Request, query: str = "", free: str = "", sort: str = "name"):
    models = list_favorite_models(query=query or None, free_only=(free == "1"), sort=sort)
    return templates.TemplateResponse(
        request, "partials/favorites_results.html",
        {"models": models, "query": query, "free": free == "1", "sort": sort},
    )


@router.post("/{model_id}/favorite", response_class=HTMLResponse)
async def favorite_add(request: Request, model_id: int):
    set_favorite(model_id, True)
    model = get_model(model_id)
    return templates.TemplateResponse(request, "partials/model_row.html", {"m": model})


@router.post("/{model_id}/unfavorite", response_class=HTMLResponse)
async def favorite_remove(request: Request, model_id: int, from_tab: str = ""):
    set_favorite(model_id, False)
    if from_tab == "fav":
        # wiersz znika z listy ulubionych (model zostaje w użyciu)
        return Response(status_code=200)
    model = get_model(model_id)
    return templates.TemplateResponse(request, "partials/model_row.html", {"m": model})


@router.post("/favorites/test-all", response_class=HTMLResponse)
async def favorites_test_all(request: Request):
    job_id = start_used_batch([m["id"] for m in list_favorite_models()])
    job = get_job(job_id)
    return templates.TemplateResponse(request, "partials/batch_status.html", {"job": job})


@router.post("/{model_id}/test", response_class=HTMLResponse)
async def test_model(request: Request, model_id: int, from_tab: str = ""):
    import asyncio
    # Sync wywołanie w wątku roboczym — event loop zostaje wolny dla innych
    # requestów (filtrowanie, nawigacja), a HTMX kręci spinner na przycisku.
    def _check():
        m = get_model(model_id)
        if not m:
            return
        try:
            result = run_prompt(m["model_id"], "Ping")
            update_model_status(model_id, result["status"], result.get("latency_ms"), result.get("error", ""))
        except Exception as e:
            update_model_status(model_id, "error", None, str(e))

    await asyncio.to_thread(_check)
    model = get_model(model_id)
    partial = "partials/fav_row.html" if from_tab == "fav" else "partials/model_row.html"
    return templates.TemplateResponse(request, partial, {"m": model})


@router.post("/test-all", response_class=HTMLResponse)
async def test_all(request: Request):
    # Batch w tle — panel postępu zamiast zamrożonego UI
    job_id = start_used_batch([m["id"] for m in list_ai_models()])
    job = get_job(job_id)
    return templates.TemplateResponse(request, "partials/batch_status.html", {"job": job})


@router.post("/test-selected", response_class=HTMLResponse)
async def test_selected(request: Request, selected: list[int] = Form(default=[])):
    if not selected:
        return templates.TemplateResponse(request, "partials/batch_status.html",
                                          {"job": {"id": 0, "total": 0, "done": 0, "finished": True,
                                                   "auto_add": False, "back": "used", "results": [],
                                                   "ok_count": 0, "err_count": 0, "elapsed_s": 0}})
    job_id = start_used_batch(selected)
    job = get_job(job_id)
    return templates.TemplateResponse(request, "partials/batch_status.html", {"job": job})


@router.post("/{model_id}/delete", response_class=HTMLResponse)
async def remove_model(request: Request, model_id: int):
    delete_model(model_id)
    return Response(status_code=200)


@router.get("/{model_id}/info", response_class=HTMLResponse)
async def model_info(request: Request, model_id: int):
    model = get_model(model_id)
    tags_str = ""
    if model and model.get("tags"):
        try:
            tags_str = ", ".join(json.loads(model["tags"]))
        except Exception:
            tags_str = ""
    return templates.TemplateResponse(request, "partials/model_info.html", {"m": model, "tags_str": tags_str})


@router.post("/{model_id}/notes", response_class=HTMLResponse)
async def model_notes_save(request: Request, model_id: int, notes: str = Form(""), tags: str = Form("")):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    update_model_notes(model_id, notes, tag_list)
    model = get_model(model_id)
    return templates.TemplateResponse(
        request, "partials/model_info.html",
        {"m": model, "tags_str": ", ".join(tag_list), "saved": True},
    )
