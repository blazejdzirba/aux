import time
import requests
from config import get_omniroute_api_key, get_omniroute_base

def _get_headers():
    key = get_omniroute_api_key()
    if not key:
        raise RuntimeError("Brak klucza API OmniRouter w Ustawieniach")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def run_prompt(model_id: str, prompt: str) -> dict:
    url = get_omniroute_base().rstrip("/") + "/chat/completions"
    headers = _get_headers()
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50,   # testowo mało tokenów
        "stream": False
    }
    start = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    latency = int((time.time() - start) * 1000)
    if resp.status_code == 200:
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return {"status": "ok", "text": text, "latency_ms": latency, "error": ""}
    else:
        return {"status": "error", "text": "", "latency_ms": latency, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}


def run_chat(model_id: str, messages: list) -> dict:
    """Czat Playground: wysyła pełną historię konwersacji [{role, content}] do OmniRouter."""
    url = get_omniroute_base().rstrip("/") + "/chat/completions"
    headers = _get_headers()
    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 2000,  # pełne odpowiedzi czatu (run_prompt zostawia 50 dla testów łączności)
        "stream": False
    }
    start = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        return {"status": "error", "text": "", "latency_ms": None, "error": str(e)}
    latency = int((time.time() - start) * 1000)
    if resp.status_code == 200:
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return {"status": "ok", "text": text, "latency_ms": latency, "error": ""}
    else:
        return {"status": "error", "text": "", "latency_ms": latency, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
