import json
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from models import (
    list_ai_models, get_model, delete_model, upsert_model, used_count,
    group_models_by_prefix, update_model_notes, get_provider_by_slug,
    update_model_status,
)
from catalog import list_used_model_ids, list_ignored_model_ids, ignore_models
from services.model_monitor import check_single_model
from services.catalog_client import fetch_catalog, group_by_provider
from services.omniroute_client import run_prompt

router = APIRouter(prefix="/models", tags=["models"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def models_page(request: Request):
    return templates.TemplateResponse(
        request, "models.html",
        {"active_page": "models", "used_count": used_count()},
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
    provider_row = get_provider_by_slug("omniroute")
    do_add = auto_add == "1"
    ephemeral: dict[str, dict] = {}
    for model_id in selected:
        try:
            result = run_prompt(model_id, "Ping")
        except Exception as e:
            result = {"status": "error", "error": str(e), "latency_ms": None}
        ephemeral[model_id] = result

        # Auto-dodaj TYLKO gdy test przeszedł pomyślnie — model, który nie
        # przeszedł testu, w ogóle nie trafia do "W użyciu" (zostaje bez zmian).
        if do_add and provider_row and result.get("status") == "ok":
            model = upsert_model(provider_row["id"], model_id)
            update_model_status(model["id"], "ok", result.get("latency_ms"), "")

    ctx = _catalog_context(query, provider, free, auto_add, ephemeral)
    return templates.TemplateResponse(request, "partials/catalog_results.html", ctx)


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
    models = list_ai_models(query=query or None, free_only=(free == "1"), sort=sort)
    groups = group_models_by_prefix(models)
    return templates.TemplateResponse(
        request, "partials/used_results.html",
        {"groups": groups, "total": len(models), "query": query, "free": free == "1", "sort": sort},
    )


@router.post("/{model_id}/test", response_class=HTMLResponse)
async def test_model(request: Request, model_id: int):
    await check_single_model(model_id)
    model = get_model(model_id)
    return templates.TemplateResponse(request, "partials/model_row.html", {"m": model})


@router.post("/test-all", response_class=HTMLResponse)
async def test_all(request: Request, query: str = Form(""), free: str = Form(""), sort: str = Form("name")):
    models = list_ai_models(query=query or None, free_only=(free == "1"), sort=sort)
    for m in models:
        await check_single_model(m["id"])
    models = list_ai_models(query=query or None, free_only=(free == "1"), sort=sort)
    groups = group_models_by_prefix(models)
    return templates.TemplateResponse(
        request, "partials/used_results.html",
        {"groups": groups, "total": len(models), "query": query, "free": free == "1", "sort": sort},
    )


@router.post("/test-selected", response_class=HTMLResponse)
async def test_selected(
    request: Request,
    selected: list[int] = Form(default=[]),
    query: str = Form(""),
    free: str = Form(""),
    sort: str = Form("name"),
):
    for mid in selected:
        await check_single_model(mid)
    models = list_ai_models(query=query or None, free_only=(free == "1"), sort=sort)
    groups = group_models_by_prefix(models)
    return templates.TemplateResponse(
        request, "partials/used_results.html",
        {"groups": groups, "total": len(models), "query": query, "free": free == "1", "sort": sort},
    )


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