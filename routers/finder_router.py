"""Wyszukiwarka: GitHub API (prawdziwe dane) + agent (raport po polsku).

- GET  /finder                 -> strona
- GET  /finder/api/finders     -> lista trybów (prompty systemowe)
- POST /finder/api/finders     -> dodaj tryb
- PUT  /finder/api/finders/{fid}    -> edytuj tryb
- DELETE /finder/api/finders/{fid}  -> usuń tryb
- POST /finder/api/search {finder_id, model_id, query, language} -> raport
"""

import json
import time

import requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import finders
from config import get_omniroute_api_key, get_omniroute_base
from models import list_ai_models

router = APIRouter(tags=["finder"])
templates = Jinja2Templates(directory="templates")

GITHUB_API = "https://api.github.com/search/repositories"
GH_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "VibeCenter-Finder"}
PER_PAGE = 10


def _err(msg):
    return JSONResponse({"status": "error", "error": msg})


@router.get("/finder", response_class=HTMLResponse)
async def finder_view(request: Request):
    try:
        models = list_ai_models(sort="name")
    except Exception:
        models = []
    try:
        modes = finders.list_finders()
    except Exception:
        modes = []
    return templates.TemplateResponse(
        request, "finder.html",
        {"request": request, "active_page": "finder", "models": models, "finders": modes},
    )


@router.get("/finder/api/finders")
async def api_list():
    try:
        return JSONResponse({"status": "ok", "finders": finders.list_finders()})
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")


@router.post("/finder/api/finders")
async def api_add(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    try:
        fid = finders.add_finder(
            body.get("name"), body.get("description"), body.get("input_hint"),
            body.get("query_template"), body.get("sort"), body.get("system_prompt"),
        )
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    return JSONResponse({"status": "ok", "id": fid})


@router.put("/finder/api/finders/{fid}")
async def api_update(fid: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    try:
        ok = finders.update_finder(
            fid, body.get("name"), body.get("description"), body.get("input_hint"),
            body.get("query_template"), body.get("sort"), body.get("system_prompt"),
        )
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    if not ok:
        return _err("Nie ma takiego trybu.")
    return JSONResponse({"status": "ok"})


@router.delete("/finder/api/finders/{fid}")
async def api_delete(fid: int):
    try:
        ok = finders.delete_finder(fid)
    except Exception as exc:
        return _err(f"Błąd bazy: {exc}")
    if not ok:
        return _err("Nie ma takiego trybu.")
    return JSONResponse({"status": "ok"})


@router.post("/finder/api/search")
async def api_search(request: Request):
    started = time.time()
    try:
        body = await request.json()
    except Exception:
        return _err("Nieprawidłowy JSON")
    query = " ".join((body.get("query") or "").split())[:200]
    language = " ".join((body.get("language") or "").split())[:30]
    model_id = (body.get("model_id") or "").strip()
    finder_id = body.get("finder_id")
    if not query:
        return _err("Wpisz opis lub nazwę do znalezienia.")
    if not model_id:
        return _err("Wybierz model.")
    try:
        mode = finders.get_finder(int(finder_id))
    except (TypeError, ValueError):
        mode = None
    if not mode:
        return _err("Nieznany tryb wyszukiwania.")

    # 1. Zapytanie do GitHub API z szablonu trybu.
    try:
        gh_q = mode["query_template"].format(q=query, lang=language)
    except Exception:
        return _err("Błędny szablon zapytania w tym trybie (dozwolone: {q}, {lang}).")
    gh_q = " ".join(gh_q.split())
    if language:
        gh_q += f" language:{language}"
    if not gh_q:
        return _err("Puste zapytanie po podstawieniu szablonu.")
    sort = mode["sort"] if mode["sort"] in ("stars", "updated") else "stars"

    try:
        resp = requests.get(GITHUB_API, headers=GH_HEADERS,
                            params={"q": gh_q, "sort": sort, "order": "desc",
                                    "per_page": PER_PAGE},
                            timeout=20)
    except requests.RequestException as exc:
        return _err(f"GitHub nie odpowiada: {exc}")
    if resp.status_code in (403, 429):
        return _err("Limit GitHub API (10 zapytań/min bez klucza) — odczekaj chwilę i spróbuj ponownie.")
    if resp.status_code != 200:
        return _err(f"GitHub zwrócił błąd HTTP {resp.status_code}.")
    try:
        data = resp.json()
        items = data.get("items", [])
        total_count = data.get("total_count", 0)
    except Exception:
        return _err("Nieoczekiwana odpowiedź GitHub.")
    repos = [{
        "name": it.get("full_name", "?"),
        "url": it.get("html_url", ""),
        "stars": it.get("stargazers_count", 0),
        "lang": it.get("language") or "—",
        "desc": (it.get("description") or "—")[:200],
        "updated": (it.get("updated_at") or "")[:10],
    } for it in items[:PER_PAGE]]
    if not repos:
        return JSONResponse({"status": "ok", "report": "", "repos": [], "total_count": 0,
                             "gh_query": gh_q, "latency_ms": 0,
                             "notice": "GitHub nic nie znalazł — spróbuj innej frazy (najlepiej po angielsku)."})

    # 2. Agent: raport po polsku na podstawie prawdziwych wyników.
    try:
        key = get_omniroute_api_key()
        base = get_omniroute_base()
    except Exception as exc:
        return _err(f"Błąd konfiguracji: {exc}")
    if not key:
        return _err("Brak klucza API w Ustawieniach.")
    user_msg = (
        f"Opis użytkownika: {query}\n\n"
        f"Wyniki z GitHub API (JSON, korzystaj TYLKO z nich):\n"
        f"{json.dumps(repos, ensure_ascii=False)}\n\n"
        "Napisz raport zgodnie z Twoją rolą."
    )
    url = (base or "").rstrip("/") + "/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": mode["system_prompt"]},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 2500,
        "stream": False,
    }
    try:
        resp = requests.post(url, headers={"Authorization": f"Bearer {key}",
                                           "Content-Type": "application/json"},
                             json=payload, timeout=120)
    except requests.RequestException as exc:
        return _err(f"Błąd połączenia z gatewayem: {exc}")
    if resp.status_code != 200:
        return _err(f"Gateway zwrócił błąd HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        report = (content or "").strip()
    except Exception:
        return _err("Nieoczekiwany format odpowiedzi z API.")
    if not report:
        return _err("Model zwrócił pustą odpowiedź.")
    return JSONResponse({"status": "ok", "report": report, "repos": repos,
                         "total_count": total_count, "gh_query": gh_q,
                         "latency_ms": int((time.time() - started) * 1000)})
