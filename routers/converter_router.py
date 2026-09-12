from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates

from config import DATA_DIR
from models import list_documents, get_document
from services.converter_service import (
    AVAILABLE_TEMPLATES,
    convert_markdown_to_pdf,
    derive_title,
    ensure_converted_dir,
)
from services.catalog_client import fetch_catalog
from services.omniroute_client import run_chat

router = APIRouter(prefix="/converter", tags=["converter"])
templates = Jinja2Templates(directory="templates")

DEFAULT_AI_MODEL = "auto/best-free"

AI_ENRICH_SYSTEM = (
    "Jesteś ekspertem od formatowania dokumentów Markdown przeznaczonych do druku PDF. "
    "Otrzymasz surowy Markdown. Twoje zadanie:\n"
    "1. Napraw hierarchię nagłówków (jeden H1 na górze, potem H2/H3 bez przeskoków).\n"
    "2. Dodaj znacznik [TOC] w osobnej linii tuż pod tytułem H1 (to wygeneruje spis treści).\n"
    "3. Popraw tabele: wyrównaj kolumny, uzupełnij puste komórki znakiem '—', "
    "upewnij się że każda tabela ma wiersz nagłówkowy i separator | --- |.\n"
    "4. Popraw listy (spójne wcięcia, myślniki), bloki kodu (dodaj język jeśli oczywisty, "
    "np. ```python), linki i cytaty.\n"
    "5. Usuń nadmiarowe puste linie (max jedna pod rząd), popraw literówki formatowania.\n"
    "ZASADY TWARDE: nie zmieniaj merytoryki, nie dopisuj nowych faktów, nie tłumacz tekstu. "
    "Odpowiedz WYŁĄCZNIE poprawionym Markdown — bez komentarzy, wyjaśnień i cudzysłowów."
)


def _catalog_models() -> list[dict]:
    try:
        return fetch_catalog()
    except Exception:
        return []


@router.get("", response_class=HTMLResponse)
async def converter_view(request: Request):
    return templates.TemplateResponse(
        request,
        "converter.html",
        {
            "active_page": "converter",
            "models": _catalog_models(),
            "docs": list_documents(),
            "templates_list": AVAILABLE_TEMPLATES,
            "default_ai_model": DEFAULT_AI_MODEL,
        },
    )


@router.get("/document/{doc_id}")
async def converter_get_document(doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        return JSONResponse({"status": "error", "error": "Nie znaleziono dokumentu."})
    return JSONResponse(
        {"status": "ok", "title": doc["title"], "content": doc.get("content", "")}
    )


def _enrich_markdown(text: str, model: str | None) -> str:
    """Czyści Markdown przez OmniRoute (TOC + tabele + struktura)."""
    use_model = (model or "").strip() or DEFAULT_AI_MODEL
    result = run_chat(
        use_model,
        [
            {"role": "system", "content": AI_ENRICH_SYSTEM},
            {"role": "user", "content": text},
        ],
    )
    if result.get("status") != "ok" or not (result.get("text") or "").strip():
        raise RuntimeError(result.get("error") or "AI zwróciło pustą odpowiedź.")
    return result["text"].strip()


@router.post("/ai-enrich")
async def converter_ai_enrich(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "text": "", "error": "Nieprawidłowy JSON"})
    text = (payload.get("text") or "").strip()
    model = (payload.get("model") or "").strip()
    if not text:
        return JSONResponse({"status": "error", "text": "", "error": "Brak tekstu do wzbogacenia."})
    try:
        enriched = _enrich_markdown(text, model)
    except Exception as e:
        return JSONResponse({"status": "error", "text": "", "error": str(e)})
    return JSONResponse({"status": "ok", "text": enriched, "error": ""})


@router.post("/md-to-pdf", response_class=HTMLResponse)
async def converter_md_to_pdf(
    request: Request,
    md_file: UploadFile | None = File(None),
    source_text: str = Form(""),
    doc_title: str = Form(""),
    template: str = Form("business"),
    page_size: str = Form("A4"),
    margins: str = Form("normal"),
    page_numbers: str = Form("0"),
    ai_enrich: str = Form("0"),
    ai_model: str = Form(""),
):
    md_text = (source_text or "").strip()
    title = (doc_title or "").strip()

    # Plik ma priorytet nad wklejonym tekstem
    if md_file is not None and md_file.filename:
        try:
            raw = await md_file.read()
            try:
                md_text = raw.decode("utf-8")
            except UnicodeDecodeError:
                md_text = raw.decode("latin-1")
            md_text = md_text.strip()
            if not title:
                fname = md_file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                title = fname.rsplit(".", 1)[0] if "." in fname else fname
        except Exception as e:
            return templates.TemplateResponse(
                request,
                "partials/converter_result.html",
                {"error": "Nie udało się odczytać pliku: %s" % e},
            )

    if not md_text:
        return templates.TemplateResponse(
            request,
            "partials/converter_result.html",
            {"error": "Brak źródła — prześlij plik .md, wybierz dokument z bazy albo wklej tekst."},
        )

    if template not in AVAILABLE_TEMPLATES:
        template = "business"

    enriched = False
    ai_warning = ""
    if ai_enrich == "1":
        try:
            md_text = _enrich_markdown(md_text, ai_model)
            enriched = True
        except Exception as e:
            ai_warning = "AI niedostępne (%s) — generuję PDF z oryginalnego tekstu." % e
        # Gwarancja spisu treści po stronie backendu (znacznik dla ekstensji toc)
        if "[TOC]" not in md_text:
            md_text = "[TOC]\n\n" + md_text

    if not title:
        title = derive_title(md_text)

    try:
        pdf_bytes = convert_markdown_to_pdf(
            md_text,
            template=template,
            page_size=page_size,
            margins=margins,
            page_numbers=(page_numbers == "1"),
            title=title,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/converter_result.html",
            {"error": str(e)},
        )

    ensure_converted_dir()
    from services.converter_service import save_pdf

    filename = save_pdf(pdf_bytes, title)

    return templates.TemplateResponse(
        request,
        "partials/converter_result.html",
        {
            "filename": filename,
            "title": title,
            "size_kb": round(len(pdf_bytes) / 1024, 1),
            "chars": len(md_text),
            "template_label": AVAILABLE_TEMPLATES.get(template, template),
            "enriched": enriched,
            "ai_warning": ai_warning,
        },
    )


@router.get("/pdf/{filename}")
async def converter_serve_pdf(filename: str, download: str = ""):
    # Ochrona przed path traversal: tylko płaska nazwa *.pdf z katalogu converted
    clean = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if clean != filename or not clean.endswith(".pdf") or ".." in clean:
        return JSONResponse({"status": "error", "error": "Nieprawidłowa nazwa pliku."}, status_code=400)
    path = DATA_DIR / "converted" / clean
    if not path.exists():
        return JSONResponse({"status": "error", "error": "Plik nie istnieje."}, status_code=404)
    if download == "1":
        return FileResponse(path, media_type="application/pdf", filename=clean)
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="%s"' % clean},
    )
