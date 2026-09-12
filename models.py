import json
import sqlite3
from database import get_db_connection

# ---------- Providers ----------
def get_provider_by_slug(slug: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM providers WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ---------- Models ----------
def list_ai_models(status: str | None = None, query: str | None = None,
                    free_only: bool = False, sort: str = "name"):
    conn = get_db_connection()
    sql = "SELECT m.*, p.name as provider_name FROM ai_models m JOIN providers p ON p.id = m.provider_id WHERE 1=1"
    params = []
    if status:
        sql += " AND m.last_status = ?"
        params.append(status)
    if query:
        sql += " AND (m.model_id LIKE ? OR m.display_name LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like])
    if free_only:
        sql += " AND m.is_free = 1"
    order = {
        "name": "m.model_id",
        "status": "m.last_status, m.model_id",
        "latency": "m.last_latency_ms IS NULL, m.last_latency_ms",
    }.get(sort, "m.model_id")
    sql += f" ORDER BY {order}"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def group_models_by_prefix(models: list[dict]) -> dict[str, list[dict]]:
    """Grupuje modele 'w użyciu' po prefiksie z model_id (np. agentrouter/xyz -> AGENTROUTER)."""
    groups: dict[str, list[dict]] = {}
    for m in models:
        prefix = m["model_id"].split("/", 1)[0].upper() if "/" in m["model_id"] else "INNE"
        groups.setdefault(prefix, []).append(m)
    return dict(sorted(groups.items()))

def used_count() -> int:
    conn = get_db_connection()
    n = conn.execute("SELECT COUNT(*) c FROM ai_models").fetchone()["c"]
    conn.close()
    return n

def get_model(model_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def upsert_model(provider_id: int, model_id: str, display_name: str = "",
                  context_length: int | None = None, is_free: bool | None = None):
    conn = get_db_connection()
    existing = conn.execute("SELECT * FROM ai_models WHERE provider_id = ? AND model_id = ?", (provider_id, model_id)).fetchone()
    if existing:
        final_free = existing["is_free"] if is_free is None else (1 if is_free else 0)
        # None = "nie ruszaj" — chroni zapisany kontekst przed wyczyszczeniem
        final_ctx = existing["context_length"] if context_length is None else context_length
        conn.execute(
            "UPDATE ai_models SET display_name = ?, context_length = ?, is_free = ?, updated_at = datetime('now') WHERE id = ?",
            (display_name or existing["display_name"], final_ctx, final_free, existing["id"]),
        )
        new_id = existing["id"]
    else:
        cur = conn.execute(
            "INSERT INTO ai_models (provider_id, model_id, display_name, context_length, is_free) VALUES (?, ?, ?, ?, ?)",
            (provider_id, model_id, display_name, context_length, 1 if is_free else 0),
        )
        new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_model(new_id)

def update_model_status(model_id: int, status: str, latency_ms: int | None = None, error: str = ""):
    conn = get_db_connection()
    conn.execute("UPDATE ai_models SET last_status = ?, last_latency_ms = ?, last_error = ?, last_checked_at = datetime('now'), is_available = ?, updated_at = datetime('now') WHERE id = ?",
                 (status, latency_ms, error, 1 if status == "ok" else 0, model_id))
    conn.execute("INSERT INTO model_status_checks (model_id, status, latency_ms, error_message) VALUES (?, ?, ?, ?)",
                 (model_id, status, latency_ms, error))
    conn.commit()
    conn.close()

def delete_model(model_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM ai_models WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()

def toggle_model_hidden(model_id: int):
    conn = get_db_connection()
    conn.execute("UPDATE ai_models SET is_hidden = 1 - is_hidden WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()

def update_model_notes(model_id: int, notes: str, tags: list[str]):
    conn = get_db_connection()
    conn.execute("UPDATE ai_models SET notes = ?, tags = ? WHERE id = ?", (notes, json.dumps(tags), model_id))
    conn.commit()
    conn.close()

def fmt_context(n) -> str:
    """Zwarty format rozmiaru kontekstu do tabel: 1M, 1.5M, 128K, 200K, —."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "—"
    if n >= 1_000_000:
        return ("%gM" % round(n / 1_000_000, 1))
    if n >= 1000:
        return ("%gK" % round(n / 1000, 1))
    return str(n)

def backfill_context_from_catalog(items: list[dict]) -> int:
    """Uzupełnia brakujące context_length/is_free w ai_models danymi z katalogu.

    Wywoływane przy otwarciu zakładki 'W użyciu' — modele dodane wcześniej
    (bez metadanych) dostają rozmiar kontekstu bez ponownego dodawania.
    Zwraca liczbę zaktualizowanych wierszy.
    """
    if not items:
        return 0
    conn = get_db_connection()
    updated = 0
    for it in items:
        try:
            cur = conn.execute(
                "UPDATE ai_models SET context_length = ?, is_free = ? "
                "WHERE model_id = ? AND context_length IS NULL",
                (it.get("context_length"), 1 if it.get("is_free") else 0, it.get("model_id")),
            )
            updated += cur.rowcount
        except Exception:
            pass
    conn.commit()
    conn.close()
    return updated

# ---------- Documents ----------
def list_documents():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, title, updated_at FROM documents ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_document(doc_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_document(title: str, content: str = ""):
    conn = get_db_connection()
    cur = conn.execute("INSERT INTO documents (title, content) VALUES (?, ?)", (title, content))
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return get_document(doc_id)

def update_document(doc_id: int, title: str, content: str):
    conn = get_db_connection()
    conn.execute("UPDATE documents SET title = ?, content = ?, updated_at = datetime('now') WHERE id = ?", (title, content, doc_id))
    conn.commit()
    conn.close()
    return get_document(doc_id)

def delete_document(doc_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

# ---------- Projects (Krok 1: lista) ----------
_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

def _ensure_projects_table(conn):
    """Leniva migracja: tabela projects tworzy się sama, bez zmian w database.py/init_db."""
    conn.execute(_PROJECTS_DDL)
    conn.commit()

def _table_has_column(conn, table: str, column: str) -> bool:
    try:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return False
    return any(c["name"] == column for c in cols)

def list_projects():
    conn = get_db_connection()
    _ensure_projects_table(conn)
    rows = conn.execute("SELECT id, title, description, updated_at FROM projects ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_project(project_id: int):
    conn = get_db_connection()
    _ensure_projects_table(conn)
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_project(title: str, description: str = ""):
    conn = get_db_connection()
    _ensure_projects_table(conn)
    cur = conn.execute("INSERT INTO projects (title, description) VALUES (?, ?)", (title, description))
    conn.commit()
    project_id = cur.lastrowid
    conn.close()
    return get_project(project_id)

def update_project(project_id: int, title: str, description: str = ""):
    conn = get_db_connection()
    _ensure_projects_table(conn)
    conn.execute("UPDATE projects SET title = ?, description = ?, updated_at = datetime('now') WHERE id = ?", (title, description, project_id))
    conn.commit()
    conn.close()
    return get_project(project_id)

def delete_project(project_id: int):
    """Usuwa projekt. Przypięte elementy (kolumna project_id z kroku 4) są odpiane, nie usuwane."""
    conn = get_db_connection()
    _ensure_projects_table(conn)
    for table in ("documents", "prompts", "notes"):
        if _table_has_column(conn, table, "project_id"):
            conn.execute(f"UPDATE {table} SET project_id = NULL WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def count_project_items(project_id: int) -> dict:
    """Liczniki elementów projektu. Zwracają zera, dopóki krok 4 nie doda kolumn project_id."""
    counts = {"prompts": 0, "documents": 0, "notes": 0}
    conn = get_db_connection()
    try:
        if _table_has_column(conn, "documents", "project_id"):
            counts["documents"] = conn.execute("SELECT COUNT(*) c FROM documents WHERE project_id = ?", (project_id,)).fetchone()["c"]
        if _table_has_column(conn, "prompts", "project_id"):
            counts["prompts"] = conn.execute("SELECT COUNT(*) c FROM prompts WHERE project_id = ?", (project_id,)).fetchone()["c"]
        if _table_has_column(conn, "notes", "project_id"):
            counts["notes"] = conn.execute("SELECT COUNT(*) c FROM notes WHERE project_id = ?", (project_id,)).fetchone()["c"]
    except Exception:
        pass
    conn.close()
    return counts

_NOTES_DDL = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
"""

def _ensure_project_id_column(conn, table: str):
    """Leniwa migracja z kroku 2: dopina kolumnę project_id jeśli jej nie ma."""
    if not _table_has_column(conn, table, "project_id"):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN project_id INTEGER REFERENCES projects(id)")
        conn.commit()

def _ensure_notes_table(conn):
    conn.execute(_NOTES_DDL)
    conn.commit()

def touch_project(project_id: int):
    """Podbija updated_at projektu (sortowanie 'ostatnio modyfikowane' działa dalej)."""
    conn = get_db_connection()
    _ensure_projects_table(conn)
    conn.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

# --- Notatki (żyją wyłącznie wewnątrz projektów) ---
def list_notes_by_project(project_id: int):
    conn = get_db_connection()
    _ensure_notes_table(conn)
    rows = conn.execute("SELECT * FROM notes WHERE project_id = ? ORDER BY updated_at DESC", (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_note(project_id: int, title: str, content: str = ""):
    conn = get_db_connection()
    _ensure_notes_table(conn)
    cur = conn.execute("INSERT INTO notes (project_id, title, content) VALUES (?, ?, ?)", (project_id, title, content))
    conn.commit()
    note_id = cur.lastrowid
    conn.close()
    return note_id

def update_note(note_id: int, title: str, content: str = ""):
    conn = get_db_connection()
    _ensure_notes_table(conn)
    conn.execute("UPDATE notes SET title = ?, content = ?, updated_at = datetime('now') WHERE id = ?", (title, content, note_id))
    conn.commit()
    conn.close()

def delete_note(note_id: int):
    conn = get_db_connection()
    _ensure_notes_table(conn)
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()

# --- Prompty (tabela saved_prompts; UWAGA: brak kolumny updated_at) ---
def list_prompts_by_project(project_id: int):
    conn = get_db_connection()
    _ensure_project_id_column(conn, "saved_prompts")
    rows = conn.execute("SELECT id, title, content, source, mode, created_at FROM saved_prompts WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_prompt_in_project(project_id: int, title: str, content: str = "", mode: str = ""):
    conn = get_db_connection()
    _ensure_project_id_column(conn, "saved_prompts")
    cur = conn.execute("INSERT INTO saved_prompts (title, content, source, mode, project_id) VALUES (?, ?, 'manual', ?, ?)", (title, content, mode, project_id))
    conn.commit()
    prompt_id = cur.lastrowid
    conn.close()
    return prompt_id

def set_prompt_project(prompt_id: int, project_id: int | None):
    conn = get_db_connection()
    _ensure_project_id_column(conn, "saved_prompts")
    conn.execute("UPDATE saved_prompts SET project_id = ? WHERE id = ?", (project_id, prompt_id))
    conn.commit()
    conn.close()

# --- Dokumenty ---
def list_documents_by_project(project_id: int):
    conn = get_db_connection()
    _ensure_project_id_column(conn, "documents")
    rows = conn.execute("SELECT id, title, updated_at FROM documents WHERE project_id = ? ORDER BY updated_at DESC", (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_document_in_project(project_id: int, title: str, content: str = ""):
    conn = get_db_connection()
    _ensure_project_id_column(conn, "documents")
    cur = conn.execute("INSERT INTO documents (title, content, project_id) VALUES (?, ?, ?)", (title, content, project_id))
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return doc_id

def set_document_project(doc_id: int, project_id: int | None):
    conn = get_db_connection()
    _ensure_project_id_column(conn, "documents")
    conn.execute("UPDATE documents SET project_id = ? WHERE id = ?", (project_id, doc_id))
    conn.commit()
    conn.close()

# --- Krok 2: poprawione wersje funkcji z kroku 1 (te definicje nadpisują starsze) ---
def delete_project(project_id: int):
    """Usuwa projekt. Przypięte elementy są odpiane (project_id = NULL), nie usuwane."""
    conn = get_db_connection()
    _ensure_projects_table(conn)
    for table in ("documents", "saved_prompts", "notes"):
        if _table_has_column(conn, table, "project_id"):
            conn.execute(f"UPDATE {table} SET project_id = NULL WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def count_project_items(project_id: int) -> dict:
    """Liczniki elementów projektu (Krok 2: właściwa tabela saved_prompts + żywe notatki)."""
    counts = {"prompts": 0, "documents": 0, "notes": 0}
    conn = get_db_connection()
    try:
        if _table_has_column(conn, "documents", "project_id"):
            counts["documents"] = conn.execute("SELECT COUNT(*) c FROM documents WHERE project_id = ?", (project_id,)).fetchone()["c"]
        if _table_has_column(conn, "saved_prompts", "project_id"):
            counts["prompts"] = conn.execute("SELECT COUNT(*) c FROM saved_prompts WHERE project_id = ?", (project_id,)).fetchone()["c"]
        _ensure_notes_table(conn)
        counts["notes"] = conn.execute("SELECT COUNT(*) c FROM notes WHERE project_id = ?", (project_id,)).fetchone()["c"]
    except Exception:
        pass
    conn.close()
    return counts
# ====================================================================
# ULUBIONE: ten plik DOPISZ na koniec models.py, NIE nadpisuj models.py!
# Uzycie (w katalogu aux):  cat models_favorites_APPEND.py >> models.py
# ====================================================================

# ---------- Ulubione modele ----------
# UWAGA: sekcja dopisywana na koniec models.py (plik models_favorites_APPEND.py).
def _ensure_favorite_column(conn):
    """Leniwa migracja: kolumna is_favorite w ai_models."""
    if not _table_has_column(conn, "ai_models", "is_favorite"):
        conn.execute("ALTER TABLE ai_models ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        conn.commit()

def set_favorite(model_id: int, fav: bool):
    conn = get_db_connection()
    _ensure_favorite_column(conn)
    conn.execute("UPDATE ai_models SET is_favorite = ?, updated_at = datetime('now') WHERE id = ?",
                 (1 if fav else 0, model_id))
    conn.commit()
    conn.close()

def list_favorite_models(query: str | None = None, free_only: bool = False, sort: str = "name"):
    """Ulubione jako płaska lista (bez grupowania), filtry jak w liście 'W użyciu'."""
    conn = get_db_connection()
    _ensure_favorite_column(conn)
    sql = "SELECT m.*, p.name as provider_name FROM ai_models m JOIN providers p ON p.id = m.provider_id WHERE m.is_favorite = 1"
    params = []
    if query:
        sql += " AND (m.model_id LIKE ? OR m.display_name LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like])
    if free_only:
        sql += " AND m.is_free = 1"
    order = {
        "name": "m.model_id",
        "status": "m.last_status, m.model_id",
        "latency": "m.last_latency_ms IS NULL, m.last_latency_ms",
    }.get(sort, "m.model_id")
    sql += f" ORDER BY {order}"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def favorite_count() -> int:
    conn = get_db_connection()
    _ensure_favorite_column(conn)
    n = conn.execute("SELECT COUNT(*) c FROM ai_models WHERE is_favorite = 1").fetchone()["c"]
    conn.close()
    return n
