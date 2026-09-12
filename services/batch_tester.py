"""Wsadowe testowanie modeli w tle (wątki), z postępem sczytywanym przez UI.

Problem, który rozwiązuje: test N modeli w jednym requeście HTMX blokuje
event loop (N × timeout). Tu testy lecą w ThreadPoolExecutor, a przeglądarka
polluje status joba co 1,5 s — wyniki widoczne na bieżąco, UI responsywne.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from models import get_model, get_provider_by_slug, upsert_model, update_model_status

_jobs: dict[int, dict] = {}
_lock = threading.Lock()
_next_id = 1
MAX_WORKERS = 6


def start_catalog_batch(model_ids: list[str], auto_add: bool = False) -> int:
    """Job dla zakładki 'Testowanie': testuje model_id z katalogu.

    auto_add=True -> modele z odpowiedzią OK trafiają do 'W użyciu'.
    """
    global _next_id
    with _lock:
        job_id = _next_id
        _next_id += 1
        _jobs[job_id] = {
            "id": job_id, "total": len(model_ids), "done": 0,
            "results": [], "finished": False, "auto_add": auto_add,
            "back": "catalog", "started_at": time.time(),
        }
    threading.Thread(target=_run_catalog, args=(job_id, list(model_ids)), daemon=True).start()
    return job_id


def start_used_batch(model_db_ids: list[int]) -> int:
    """Job dla zakładki 'W użyciu': testuje zapisane modele i aktualizuje status w DB."""
    global _next_id
    pairs = []
    for db_id in model_db_ids:
        m = get_model(db_id)
        if m:
            pairs.append((db_id, m["model_id"]))
    with _lock:
        job_id = _next_id
        _next_id += 1
        _jobs[job_id] = {
            "id": job_id, "total": len(pairs), "done": 0,
            "results": [], "finished": False, "auto_add": False,
            "back": "used", "started_at": time.time(),
        }
    threading.Thread(target=_run_used, args=(job_id, pairs), daemon=True).start()
    return job_id


def _test_model_id(model_id: str) -> dict:
    from services.omniroute_client import run_prompt
    try:
        result = run_prompt(model_id, "Ping")
    except Exception as e:
        result = {"status": "error", "error": str(e), "latency_ms": None}
    return {
        "model_id": model_id,
        "status": result.get("status", "error"),
        "latency_ms": result.get("latency_ms"),
        "error": (result.get("error") or "")[:200],
    }


def _run_catalog(job_id: int, model_ids: list[str]) -> None:
    job = _jobs[job_id]
    provider_row = get_provider_by_slug("omniroute")

    # Metadane z katalogu (cache) — żeby modele dodane do 'W użyciu'
    # od razu miały rozmiar kontekstu i flagę FREE.
    meta: dict[str, dict] = {}
    try:
        from services.catalog_client import fetch_catalog
        for it in fetch_catalog():
            meta[it["model_id"]] = it
    except Exception:
        pass

    def one(mid: str) -> dict:
        r = _test_model_id(mid)
        if job["auto_add"] and provider_row and r["status"] == "ok":
            try:
                info = meta.get(mid) or {}
                m = upsert_model(
                    provider_row["id"], mid,
                    context_length=info.get("context_length"),
                    is_free=bool(info.get("is_free")) if info else None,
                )
                update_model_status(m["id"], "ok", r["latency_ms"], "")
            except Exception:
                pass
        return r

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for r in ex.map(one, model_ids):
            with _lock:
                job["results"].append(r)
                job["done"] += 1
    job["finished"] = True


def _run_used(job_id: int, pairs: list[tuple[int, str]]) -> None:
    job = _jobs[job_id]

    def one(pair: tuple[int, str]) -> dict:
        db_id, model_id = pair
        r = _test_model_id(model_id)
        try:
            update_model_status(db_id, r["status"], r["latency_ms"], r["error"])
        except Exception:
            pass
        return r

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for r in ex.map(one, pairs):
            with _lock:
                job["results"].append(r)
                job["done"] += 1
    job["finished"] = True


def get_job(job_id: int) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        results = sorted(job["results"], key=lambda r: r["model_id"])
        return {
            "id": job["id"],
            "total": job["total"],
            "done": job["done"],
            "finished": job["finished"],
            "auto_add": job["auto_add"],
            "back": job["back"],
            "results": results,
            "ok_count": sum(1 for r in results if r["status"] == "ok"),
            "err_count": sum(1 for r in results if r["status"] != "ok"),
            "elapsed_s": int(time.time() - job["started_at"]),
        }
