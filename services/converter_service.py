"""Konwerter Markdown -> PDF (AUX).

Pipeline: Markdown tekst -> HTML (biblioteka `markdown`) -> PDF (WeasyPrint,
z fallbackiem do xhtml2pdf).

Szablony CSS do PDF leżą w: templates/pdf_styles/*.css
Wygenerowane pliki PDF: data/converted/*.pdf
"""
import time
import uuid
import html as html_lib
from pathlib import Path

from config import APP_DIR, DATA_DIR

AVAILABLE_TEMPLATES = {
    "business": "Elegancki Biznesowy",
    "tech": "Nowoczesny / Tech",
    "minimal": "Minimalistyczny",
    "dark": "Ciemny / AUX Style",
}

PAGE_SIZES = ["A4", "Letter"]

MARGINS = {
    "narrow": "12mm",
    "normal": "20mm",
    "wide": "30mm",
}

CONVERTED_DIRNAME = "converted"
MAX_KEPT_PDFS = 50


def ensure_converted_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / CONVERTED_DIRNAME
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_template_css(template: str) -> str:
    name = template if template in AVAILABLE_TEMPLATES else "business"
    css_path = APP_DIR / "templates" / "pdf_styles" / (name + ".css")
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return ""


def markdown_to_html(md_text: str) -> str:
    import markdown

    return markdown.markdown(
        md_text,
        extensions=["extra", "tables", "fenced_code", "toc", "sane_lists"],
    )


def build_print_html(
    md_text: str,
    template: str = "business",
    page_size: str = "A4",
    margins: str = "normal",
    page_numbers: bool = True,
    title: str = "Dokument",
) -> str:
    """Składa pełny dokument HTML gotowy do druku (HTML + CSS -> PDF)."""
    body_html = markdown_to_html(md_text)
    template_css = get_template_css(template)

    size = page_size if page_size in PAGE_SIZES else "A4"
    margin_value = MARGINS.get(margins, MARGINS["normal"])

    # Reguła @page doklejana PO css szablonu, żeby nadpisać rozmiar/marginesy.
    # (WeasyPrint łączy reguły @page kaskadowo; xhtml2pdf nie rozumie
    # @bottom-center i po prostu ją zignoruje.)
    page_css = "@page { size: " + size + "; margin: " + margin_value + ";"
    if page_numbers:
        page_css += (
            ' @bottom-center { content: counter(page) " / " counter(pages);'
            " font-size: 8pt; color: #888; font-family: sans-serif; }"
        )
    page_css += " }"

    safe_title = html_lib.escape(title or "Dokument")
    full_css = template_css + "\n\n" + page_css

    return (
        "<!DOCTYPE html>\n"
        '<html lang="pl">\n<head>\n'
        '<meta charset="utf-8">\n'
        "<title>" + safe_title + "</title>\n"
        "<style>\n" + full_css + "\n</style>\n"
        "</head>\n<body>\n"
        '<div class="pdf-content">\n' + body_html + "\n</div>\n"
        "</body>\n</html>"
    )


def html_to_pdf_bytes(print_html: str) -> bytes:
    """HTML -> PDF. Najpierw WeasyPrint, potem fallback xhtml2pdf."""
    errors: list[str] = []

    # 1) WeasyPrint (najlepsza jakość, wymaga bibliotek systemowych Pango/Cairo)
    try:
        from weasyprint import HTML as WeasyHTML

        pdf = WeasyHTML(string=print_html).write_pdf()
        if pdf:
            return bytes(pdf)
        errors.append("WeasyPrint zwrócił pusty wynik.")
    except ImportError as e:
        errors.append("WeasyPrint nie jest zainstalowany (%s)." % e)
    except Exception as e:  # np. brak libpango/libgdk na systemie
        errors.append("WeasyPrint błąd: %s" % e)

    # 2) Fallback: xhtml2pdf (czysty Python + reportlab, łatwiejszy na Windows)
    try:
        from io import BytesIO

        from xhtml2pdf import pisa

        buffer = BytesIO()
        status = pisa.CreatePDF(print_html, dest=buffer)
        if status.err:
            errors.append("xhtml2pdf zgłosił %d błędów." % status.err)
        else:
            data = buffer.getvalue()
            if data:
                return data
            errors.append("xhtml2pdf zwrócił pusty wynik.")
    except ImportError as e:
        errors.append("xhtml2pdf nie jest zainstalowany (%s)." % e)
    except Exception as e:
        errors.append("xhtml2pdf błąd: %s" % e)

    raise RuntimeError(
        "Nie udało się wygenerować PDF. "
        + " ".join(errors)
        + " Zainstaluj: pip install weasyprint xhtml2pdf"
          " (Linux: dodatkowo libpango + libgdk-pixbuf, np."
          " `sudo apt install libpango-1.0-0 libharfbuzz-subset0 libjpeg-dev libopenjp2-7-dev libffi-dev`)."
    )


def convert_markdown_to_pdf(
    md_text: str,
    template: str = "business",
    page_size: str = "A4",
    margins: str = "normal",
    page_numbers: bool = True,
    title: str = "Dokument",
) -> bytes:
    print_html = build_print_html(
        md_text,
        template=template,
        page_size=page_size,
        margins=margins,
        page_numbers=page_numbers,
        title=title,
    )
    return html_to_pdf_bytes(print_html)


def save_pdf(pdf_bytes: bytes, title: str = "") -> str:
    """Zapisuje PDF do data/converted/ i zwraca nazwę pliku."""
    out_dir = ensure_converted_dir()
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in (title or "dokument"))
    safe = (safe.strip("-") or "dokument")[:40]
    filename = "%d_%s_%s.pdf" % (int(time.time()), safe, uuid.uuid4().hex[:6])
    (out_dir / filename).write_bytes(pdf_bytes)
    cleanup_old_pdfs(out_dir)
    return filename


def cleanup_old_pdfs(out_dir: Path | None = None, keep: int = MAX_KEPT_PDFS) -> None:
    try:
        d = out_dir or ensure_converted_dir()
        pdfs = sorted(d.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in pdfs[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        pass


def derive_title(md_text: str, fallback: str = "Dokument") -> str:
    """Tytuł PDF: pierwsze H1 z markdown albo fallback (np. nazwa pliku)."""
    for line in (md_text or "").splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip() or fallback
    return fallback
