import json
import os
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = APP_DIR / "config.json"
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "aux.db"

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        default = {"omniroute_api_key": ""}
        save_config(default)
        return default
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def get_omniroute_api_key() -> str:
    # Vault ma priorytet (usługa "omniroute") — jeśli nic tam nie ma, fallback
    # do starego config.json / strony Ustawienia, żeby nic się nie wysypało.
    try:
        from vault import get_primary_key_for_service
        vault_key = get_primary_key_for_service("omniroute")
        if vault_key:
            return vault_key
    except Exception:
        pass
    return load_config().get("omniroute_api_key", "")

def set_omniroute_api_key(key: str | None) -> None:
    config = load_config()
    if key and key.strip():
        config["omniroute_api_key"] = key.strip()
    else:
        config["omniroute_api_key"] = ""
    save_config(config)

def get_db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH