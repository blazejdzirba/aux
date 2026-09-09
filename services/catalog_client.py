"""Pobiera i cache'uje katalog modeli z endpointu OmniRoute (GET /v1/models)."""
import time
import requests
from config import get_omniroute_api_key, get_omniroute_base

_cache: dict = {"items": None, "ts": 0.0}
TTL_SECONDS = 300


def _is_free(model_id: str, pricing: dict) -> bool:
    if model_id.endswith(":free"):
        return True
    prompt_price = str(pricing.get("prompt", "1"))
    completion_price = str(pricing.get("completion", "1"))
    return prompt_price in ("0", "0.0", "0.00") and completion_price in ("0", "0.0", "0.00")


def clear_cache() -> None:
    _cache["items"] = None
    _cache["ts"] = 0.0


def fetch_catalog(force: bool = False) -> list[dict]:
    now = time.time()
    if not force and _cache["items"] is not None and (now - _cache["ts"]) < TTL_SECONDS:
        return _cache["items"]

    url = get_omniroute_base().rstrip("/") + "/models"
    key = get_omniroute_api_key()
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    raw = resp.json().get("data", [])

    items = []
    for m in raw:
        mid = m.get("id", "")
        if "/" not in mid:
            continue
        prefix, _, name = mid.partition("/")
        items.append({
            "model_id": mid,
            "provider_prefix": prefix.upper(),
            "model_name": name,
            "context_length": m.get("context_length"),
            "is_free": _is_free(mid, m.get("pricing") or {}),
        })
    items.sort(key=lambda x: (x["provider_prefix"], x["model_id"]))

    _cache["items"] = items
    _cache["ts"] = now
    return items


def group_by_provider(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["provider_prefix"], []).append(it)
    return dict(sorted(groups.items()))
