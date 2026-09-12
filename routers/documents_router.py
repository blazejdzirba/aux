import markdown
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from models import list_documents, get_document, create_document, update_document, delete_document

router = APIRouter(prefix="/documents", tags=["documents"])
templates = Jinja2Templates(directory="templates")


def _ctx(request: Request, **extra) -> dict:
    return {"request": request, "docs": list_documents(), "active_page": "documents", **extra}


@router.get("", response_class=HTMLResponse)
async def documents_view(request: Request):
    return templates.TemplateResponse(request, "documents.html", _ctx(request))


@router.post("")
async def document_create(request: Request, title: str = Form("")):
    doc = create_document(title.strip() or "Bez tytułu")
    return RedirectResponse(f"/documents/{doc['id']}/edit", status_code=303)


@router.post("/upload")
async def document_upload(md_file: UploadFile = File(...)):
    raw = await md_file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
    fname = (md_file.filename or "dokument.md").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    title = fname.rsplit(".", 1)[0] if "." in fname else fname
    doc = create_document(title.strip() or "Bez tytułu", content)
    return RedirectResponse(f"/documents/{doc['id']}/edit", status_code=303)


@router.get("/{doc_id}", response_class=HTMLResponse)
async def document_preview(request: Request, doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        return RedirectResponse("/documents", status_code=303)
    rendered = markdown.markdown(doc["content"], extensions=["extra", "nl2br"])
    return templates.TemplateResponse(request, "documents.html", _ctx(request, doc=doc, rendered=rendered))


@router.get("/{doc_id}/edit", response_class=HTMLResponse)
async def document_edit(request: Request, doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        return RedirectResponse("/documents", status_code=303)
    rendered = markdown.markdown(doc["content"], extensions=["extra", "nl2br"])
    return templates.TemplateResponse(request, "documents.html", _ctx(request, doc=doc, editing=True, rendered=rendered))


@router.put("/{doc_id}", response_class=HTMLResponse)
async def document_update(request: Request, doc_id: int, title: str = Form(...), content: str = Form("")):
    doc = update_document(doc_id, title, content)
    if not doc:
        # dokument zniknął z bazy (np. usunięty w innej karcie) — wracamy na listę
        if request.headers.get("HX-Request") == "true":
            return Response(status_code=200, headers={"HX-Redirect": "/documents"})
        return RedirectResponse("/documents", status_code=303)
    if request.headers.get("HX-Request") == "true":
        rendered = markdown.markdown(doc["content"], extensions=["extra", "nl2br"])
        return templates.TemplateResponse(
            request, "partials/document_editor.html",
            {"request": request, "doc": doc, "rendered": rendered, "saved": True},
        )
    return RedirectResponse(f"/documents/{doc_id}/edit", status_code=303)


@router.delete("/{doc_id}")
async def document_delete(request: Request, doc_id: int):
    delete_document(doc_id)
    if request.headers.get("HX-Request") == "true":
        # HX-Redirect: przeglądarka przechodzi na listę (usuwanie z edytora i z listy)
        return Response(status_code=200, headers={"HX-Redirect": "/documents"})
    return RedirectResponse("/documents", status_code=303)
