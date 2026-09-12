import os
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

import project_tree
from config import get_omniroute_api_key, get_omniroute_base
from models import (
    list_projects, get_project, create_project,
    update_project, delete_project, count_project_items,
    list_notes_by_project, create_note, update_note, delete_note,
    list_prompts_by_project, create_prompt_in_project, set_prompt_project,
    list_documents_by_project, create_document_in_project, set_document_project,
    list_ai_models,
    touch_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])
templates = Jinja2Templates(directory="templates")

TABS = ("notes", "prompts", "documents", "tree")


def _fmt_dt(value: str | None) -> str:
    """SQLite datetime('now') -> '12.09.2026 02:30'. Odporne na puste/złe dane."""
    if not value:
        return "—"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:19], fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue
    return value[:16]


def _ctx(request: Request, **extra) -> dict:
    return {"request": request, "active_page": "projects", **extra}


# ==================== Krok 1: lista ====================
@router.get("", response_class=HTMLResponse)
async def projects_view(request: Request):
    projects = list_projects()
    for p in projects:
        p["counts"] = count_project_items(p["id"])
        p["updated_display"] = _fmt_dt(p.get("updated_at"))
    return templates.TemplateResponse(request, "projects.html", _ctx(request, projects=projects))


@router.post("")
async def project_create(title: str = Form(""), description: str = Form("")):
    create_project(title.strip() or "Bez tytułu", description.strip())
    return RedirectResponse("/projects", status_code=303)


@router.post("/{project_id}/update")
async def project_update(project_id: int, title: str = Form(""), description: str = Form("")):
    update_project(project_id, title.strip() or "Bez tytułu", description.strip())
    return RedirectResponse("/projects", status_code=303)


@router.post("/{project_id}/delete")
async def project_delete(project_id: int):
    delete_project(project_id)
    return RedirectResponse("/projects", status_code=303)


# ==================== Krok 2: detal z zakładkami ====================
@router.get("/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int, tab: str = "notes",
                         tmsg: str = "", tok: str = "1"):
    project = get_project(project_id)
    if not project:
        return RedirectResponse("/projects", status_code=303)
    if tab not in TABS:
        tab = "notes"
    project["updated_display"] = _fmt_dt(project.get("updated_at"))
    notes = list_notes_by_project(project_id)
    for n in notes:
        n["updated_display"] = _fmt_dt(n.get("updated_at"))
    prompts = list_prompts_by_project(project_id)
    for pr in prompts:
        pr["created_display"] = _fmt_dt(pr.get("created_at"))
    documents = list_documents_by_project(project_id)
    for d in documents:
        d["updated_display"] = _fmt_dt(d.get("updated_at"))
    tree = None
    tree_models = []
    if tab == "tree":
        root = project_tree.get_root(project_id)
        tree = {"root": root, "error": "", "bundle": None, "msg": tmsg, "msg_ok": tok == "1"}
        if root:
            if os.path.isdir(root):
                tree["bundle"] = project_tree.describe(root)
            else:
                tree["error"] = "Zapisany katalog już nie istnieje: " + root
        try:
            tree_models = list_ai_models(sort="name")
        except Exception:
            tree_models = []
    return templates.TemplateResponse(request, "project_detail.html", _ctx(
        request, project=project, notes=notes, prompts=prompts,
        documents=documents, tab=tab, tree=tree, tree_models=tree_models,
        counts={"notes": len(notes), "prompts": len(prompts), "documents": len(documents)}))


@router.post("/{project_id}/notes")
async def note_create(project_id: int, title: str = Form(""), content: str = Form("")):
    if not get_project(project_id):
        return RedirectResponse("/projects", status_code=303)
    create_note(project_id, title.strip() or "Bez tytułu", content)
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=notes", status_code=303)


@router.post("/{project_id}/notes/{note_id}/update")
async def note_update(project_id: int, note_id: int, title: str = Form(""), content: str = Form("")):
    update_note(note_id, title.strip() or "Bez tytułu", content)
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=notes", status_code=303)


@router.post("/{project_id}/notes/{note_id}/delete")
async def note_delete(project_id: int, note_id: int):
    delete_note(note_id)
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=notes", status_code=303)


@router.post("/{project_id}/prompts")
async def prompt_create_in_project(project_id: int, title: str = Form(""), content: str = Form(""), mode: str = Form("")):
    if not get_project(project_id):
        return RedirectResponse("/projects", status_code=303)
    create_prompt_in_project(project_id, title.strip() or "Bez tytułu", content, mode.strip())
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=prompts", status_code=303)


@router.post("/{project_id}/prompts/{prompt_id}/unassign")
async def prompt_unassign(project_id: int, prompt_id: int):
    set_prompt_project(prompt_id, None)
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=prompts", status_code=303)


@router.post("/{project_id}/documents")
async def document_create_in_project(project_id: int, title: str = Form(""), content: str = Form("")):
    if not get_project(project_id):
        return RedirectResponse("/projects", status_code=303)
    create_document_in_project(project_id, title.strip() or "Bez tytułu", content)
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=documents", status_code=303)


@router.post("/{project_id}/documents/{doc_id}/unassign")
async def document_unassign(project_id: int, doc_id: int):
    set_document_project(doc_id, None)
    touch_project(project_id)
    return RedirectResponse(f"/projects/{project_id}?tab=documents", status_code=303)


# ==================== Krok 3: drzewo projektu ====================
@router.post("/{project_id}/tree/root")
async def tree_set_root(project_id: int, root_path: str = Form("")):
    if not get_project(project_id):
        return RedirectResponse("/projects", status_code=303)
    ok, msg = project_tree.set_root(project_id, root_path)
    touch_project(project_id)
    return RedirectResponse(
        f"/projects/{project_id}?tab=tree&tmsg={quote(msg)}&tok={'1' if ok else '0'}",
        status_code=303)


@router.get("/{project_id}/tree/script")
async def tree_get_script(project_id: int):
    if not get_project(project_id):
        return RedirectResponse("/projects", status_code=303)
    return PlainTextResponse(
        project_tree.BUILD_CONTEXT_TEMPLATE,
        headers={"Content-Disposition": 'attachment; filename="build_context.py"'},
    )


@router.post("/{project_id}/tree/tune")
async def tree_tune(request: Request, project_id: int):
    project = get_project(project_id)
    if not project:
        return JSONResponse({"status": "error", "error": "Nie ma takiego projektu."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "error": "Nieprawidłowy JSON"})
    model_id = (body.get("model_id") or "").strip()
    if not model_id:
        return JSONResponse({"status": "error", "error": "Wybierz model."})
    root = project_tree.get_root(project_id)
    if not root or not os.path.isdir(root):
        return JSONResponse({"status": "error", "error": "Ustaw najpierw poprawny katalog projektu."})
    try:
        key = get_omniroute_api_key()
        base = get_omniroute_base()
    except Exception as exc:
        return JSONResponse({"status": "error", "error": f"Błąd konfiguracji: {exc}"})
    if not key:
        return JSONResponse({"status": "error", "error": "Brak klucza API w Ustawieniach."})
    bundle = project_tree.describe(root)
    ok, result = project_tree.tune_script(bundle["tree"]["text"], bundle["stats"], model_id, key, base)
    if not ok:
        return JSONResponse({"status": "error", "error": result})
    return JSONResponse({"status": "ok", "script": result})


@router.get("/{project_id}/tree/blueprint")
async def tree_blueprint(project_id: int, f: str = "full_app.md"):
    project = get_project(project_id)
    if not project:
        return RedirectResponse("/projects", status_code=303)
    root = project_tree.get_root(project_id)
    content = project_tree.read_blueprint_file(root, f) if root else None
    if content is None:
        return RedirectResponse(
            f"/projects/{project_id}?tab=tree&tmsg={quote('Brak pliku ' + f)}&tok=0",
            status_code=303)
    return PlainTextResponse(
        content, headers={"Content-Disposition": f'attachment; filename="{f}"'})
