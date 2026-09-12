import time
import requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from config import get_omniroute_api_key, get_omniroute_base
from models import list_ai_models

router = APIRouter(tags=["translator"])
templates = Jinja2Templates(directory="templates")

SYSTEM_PROMPTS = {
    "pl-en": (
        "You are a professional translator translating from Polish to English. "
        "Respond with ONLY the translated text — no comments, introductions or explanations. "
        "Preserve the original meaning, tone and formatting exactly "
        "(line breaks, lists, Markdown, code blocks, commands and variable names — "
        "leave code untouched). If a fragment is already in English, keep it as is. "
        "Translate the ENTIRE text \u2014 never summarize, skip or omit anything; "
        "keep the original capitalization of filenames."
    ),
    "en-pl": (
        "Jesteś profesjonalnym tłumaczem tłumaczącym z angielskiego na polski. "
        "Odpowiedz WYŁĄCZNIE przetłumaczonym tekstem — bez komentarzy, wstępów i wyjaśnień. "
        "Zachowaj dokładnie oryginalne znaczenie, ton i formatowanie "
        "(podziały linii, listy, Markdown, bloki kodu, komendy i nazwy zmiennych — "
        "kodu nie ruszaj). Fragmenty już po polsku zostaw bez zmian. "
        "Przetłumacz CAŁY tekst \u2014 nie streszczaj i niczego nie pomijaj; "
        "zachowaj oryginalną kapitalizację nazw plików."
    ),
}

STRICT_SUFFIX = (
    " CRITICAL: translate absolutely EVERYTHING \u2014 do not skip, summarize, shorten "
    "or end early. Every heading, paragraph, table row, list item and code block "
    "from the input must appear in the translation."
)

# Lazy tiktoken: brak pakietu = tryb szacunkowy, apka działa normalnie.
_TIK = None
_TIK_OK = None


def _encoder():
    global _TIK, _TIK_OK
    if _TIK_OK is None:
        try:
            import tiktoken
            _TIK = tiktoken.get_encoding("cl100k_base")
            _TIK_OK = True
        except Exception:
            _TIK_OK = False
    return _TIK if _TIK_OK else None


@router.get("/translator", response_class=HTMLResponse)
async def translator_view(request: Request):
    try:
        models = list_ai_models(sort="name")
    except Exception:
        models = []
    return templates.TemplateResponse(
        request, "translator.html",
        {"request": request, "active_page": "translator", "models": models},
    )


@router.post("/translator/translate")
async def translator_translate(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "translation": "", "error": "Nieprawidłowy JSON"})
    text = (body.get("text") or "").strip()
    direction = body.get("direction") or ""
    model_id = (body.get("model_id") or "").strip()
    strict = bool(body.get("strict"))
    if not text:
        return JSONResponse({"status": "error", "translation": "", "error": "Wklej tekst do przetłumaczenia."})
    if direction not in SYSTEM_PROMPTS:
        return JSONResponse({"status": "error", "translation": "", "error": "Nieznany kierunek tłumaczenia."})
    if not model_id:
        return JSONResponse({"status": "error", "translation": "", "error": "Wybierz model."})
    try:
        key = get_omniroute_api_key()
        base = get_omniroute_base()
    except Exception as e:
        return JSONResponse({"status": "error", "translation": "", "error": f"Błąd konfiguracji: {e}"})
    if not key:
        return JSONResponse({"status": "error", "translation": "", "error": "Brak klucza API w Ustawieniach."})
    # Limit wyjścia skalowany do wejścia (części do ~4000 znaków), z bezpiecznym sufitem.
    system = SYSTEM_PROMPTS[direction]
    max_tokens = min(8000, max(2000, len(text) // 3))
    if strict:  # retry podejrzanej części: mocniejszy prompt + więcej tokenów
        system += STRICT_SUFFIX
        max_tokens = min(8000, max(4000, len(text) // 2))
    url = (base or "").rstrip("/") + "/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    start = time.time()
    try:
        resp = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                             json=payload, timeout=120)
    except requests.RequestException as e:
        return JSONResponse({"status": "error", "translation": "", "error": f"Błąd połączenia: {e}"})
    latency_ms = int((time.time() - start) * 1000)
    if resp.status_code != 200:
        return JSONResponse({"status": "error", "translation": "",
                             "error": f"Błąd HTTP {resp.status_code}: {resp.text[:200]}"})
    try:
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        translation = (choice.get("message") or {}).get("content", "")
        if isinstance(translation, list):  # content blocks
            translation = "".join(p.get("text", "") for p in translation if isinstance(p, dict))
        translation = (translation or "").strip()
        finish_reason = choice.get("finish_reason", "")
    except Exception:
        return JSONResponse({"status": "error", "translation": "", "error": "Nieoczekiwany format odpowiedzi z API."})
    if not translation:
        return JSONResponse({"status": "error", "translation": "", "error": "Model zwrócił pustą odpowiedź."})
    return JSONResponse({"status": "ok", "translation": translation, "latency_ms": latency_ms, "error": "",
                         "finish_reason": finish_reason, "in_chars": len(text), "out_chars": len(translation)})


@router.post("/translator/count")
async def translator_count(request: Request):
    """Ile tokenów wejściowych zużyje tekst (cl100k_base; bez pakietu — szacunek)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"tokens": 0, "estimated": True})
    text = body.get("text") or ""
    enc = _encoder()
    if enc is not None:
        try:
            return JSONResponse({"tokens": len(enc.encode(text)), "estimated": False})
        except Exception:
            pass
    return JSONResponse({"tokens": int(round(len(text) / 3.5)), "estimated": True})
