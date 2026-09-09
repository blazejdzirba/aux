import markdown
from fastapi import APIRouter, Request, Form
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


@router.get("/{doc_id}", response_class=HTMLResponse)
async def document_preview(request: Request, doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        return RedirectResponse("/documents", status_code=303)
    rendered = markdown.markdown(doc["content"], extensions=["extra"])
    return templates.TemplateResponse(request, "documents.html", _ctx(request, doc=doc, rendered=rendered))


@router.get("/{doc_id}/edit", response_class=HTMLResponse)
async def document_edit(request: Request, doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        return RedirectResponse("/documents", status_code=303)
    rendered = markdown.markdown(doc["content"], extensions=["extra"])
    return templates.TemplateResponse(request, "documents.html", _ctx(request, doc=doc, editing=True, rendered=rendered))


@router.put("/{doc_id}", response_class=HTMLResponse)
async def document_update(request: Request, doc_id: int, title: str = Form(...), content: str = Form("")):
    doc = update_document(doc_id, title, content)
    if request.headers.get("HX-Request") == "true":
        rendered = markdown.markdown(doc["content"], extensions=["extra"])
        return templates.TemplateResponse(
            request, "partials/document_editor.html",
            {"request": request, "doc": doc, "rendered": rendered, "saved": True},
        )
    return RedirectResponse(f"/documents/{doc_id}/edit", status_code=303)


@router.delete("/{doc_id}")
async def document_delete(request: Request, doc_id: int):
    delete_document(doc_id)
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200)
    return RedirectResponse("/documents", status_code=303)
