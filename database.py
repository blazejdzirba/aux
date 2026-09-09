import sqlite3
from pathlib import Path
from config import get_db_path

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db() -> None:
    conn = get_db_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        kind TEXT NOT NULL DEFAULT 'omniroute',
        base_url TEXT NOT NULL DEFAULT 'https://openrouter.ai/api',
        chat_endpoint TEXT DEFAULT '/v1/chat/completions',
        models_endpoint TEXT DEFAULT '/v1/models',
        is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS ai_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
        model_id TEXT NOT NULL,
        display_name TEXT DEFAULT '',
        context_length INTEGER,
        is_available INTEGER DEFAULT 0,
        last_status TEXT DEFAULT 'unknown',
        last_latency_ms INTEGER,
        last_error TEXT,
        last_checked_at TEXT,
        notes TEXT,
        tags TEXT DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        is_hidden INTEGER DEFAULT 0,
        UNIQUE(provider_id, model_id)
    );
    CREATE TABLE IF NOT EXISTS model_status_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id INTEGER NOT NULL REFERENCES ai_models(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        latency_ms INTEGER,
        error_message TEXT,
        tokens_used INTEGER,
        checked_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS vault_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT NOT NULL,
        env_var TEXT NOT NULL,
        api_key TEXT NOT NULL,
        tags TEXT DEFAULT '',
        is_primary INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        last_used_at TEXT
    );
    CREATE TABLE IF NOT EXISTS catalog_ignored (
        model_id TEXT PRIMARY KEY,
        ignored_at TEXT DEFAULT (datetime('now'))
    );
    """)
    # Migracje kolumn dodanych po pierwszym utworzeniu bazy
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(ai_models)")]
    if "is_hidden" not in cols:
        conn.execute("ALTER TABLE ai_models ADD COLUMN is_hidden INTEGER DEFAULT 0")
    if "is_free" not in cols:
        conn.execute("ALTER TABLE ai_models ADD COLUMN is_free INTEGER DEFAULT 0")
    # Wstaw domyślnego providera omniroute
    conn.execute("INSERT OR IGNORE INTO providers (name, slug, kind, base_url, chat_endpoint, models_endpoint) VALUES ('OmniRoute', 'omniroute', 'omniroute', 'https://openrouter.ai/api', '/v1/chat/completions', '/v1/models')")
    conn.commit()
    conn.close()