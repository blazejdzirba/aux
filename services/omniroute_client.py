import time
import requests
from config import get_omniroute_api_key
from models import get_provider_by_slug

def _get_headers():
    key = get_omniroute_api_key()
    if not key:
        raise RuntimeError("Brak klucza API OmniRouter w Ustawieniach")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def run_prompt(model_id: str, prompt: str) -> dict:
    provider = get_provider_by_slug("omniroute")
    if not provider:
        raise RuntimeError("Provider omniroute nie istnieje w bazie")
    url = provider["base_url"].rstrip("/") + provider["chat_endpoint"]
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
