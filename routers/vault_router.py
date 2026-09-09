from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from vault import (
    list_vault_keys, get_vault_key, create_vault_key, update_vault_key,
    delete_vault_key, export_env_text,
)

router = APIRouter(prefix="/vault", tags=["vault"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def vault_page(request: Request, q: str = ""):
    keys = list_vault_keys(q or None)
    return templates.TemplateResponse(request, "vault.html", {"active_page": "vault", "keys": keys, "query": q})


@router.get("/table", response_class=HTMLResponse)
async def vault_table(request: Request, q: str = ""):
    keys = list_vault_keys(q or None)
    return templates.TemplateResponse(request, "partials/vault_table.html", {"keys": keys})


@router.post("", response_class=HTMLResponse)
async def vault_create(
    request: Request,
    service_name: str = Form(...),
    env_var: str = Form(...),
    api_key: str = Form(...),
    tags: str = Form(""),
    is_primary: str = Form("0"),
):
    create_vault_key(service_name, env_var, api_key, tags, is_primary == "1")
    keys = list_vault_keys()
    return templates.TemplateResponse(request, "partials/vault_table.html", {"keys": keys})


@router.put("/{key_id}", response_class=HTMLResponse)
async def vault_update(
    request: Request,
    key_id: int,
    service_name: str = Form(...),
    env_var: str = Form(...),
    api_key: str = Form(""),
    tags: str = Form(""),
    is_primary: str = Form("0"),
):
    update_vault_key(key_id, service_name, env_var, api_key or None, tags, is_primary == "1")
    k = get_vault_key(key_id)
    return templates.TemplateResponse(request, "partials/vault_row.html", {"k": k})


@router.delete("/{key_id}")
async def vault_delete(key_id: int):
    delete_vault_key(key_id)
    return Response(status_code=200)


@router.get("/export")
async def vault_export():
    content = export_env_text()
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=.env"},
    )