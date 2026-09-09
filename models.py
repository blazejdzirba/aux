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
def list_ai_models(status: str | None = None, query: str | None = None):
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
    sql += " ORDER BY m.display_name, m.model_id"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_model(model_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def upsert_model(provider_id: int, model_id: str, display_name: str = "", context_length: int | None = None):
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM ai_models WHERE provider_id = ? AND model_id = ?", (provider_id, model_id)).fetchone()
    if existing:
        conn.execute("UPDATE ai_models SET display_name = ?, context_length = ?, updated_at = datetime('now') WHERE id = ?",
                     (display_name or existing["display_name"], context_length, existing["id"]))
        new_id = existing["id"]
    else:
        cur = conn.execute("INSERT INTO ai_models (provider_id, model_id, display_name, context_length) VALUES (?, ?, ?, ?)",
                           (provider_id, model_id, display_name, context_length))
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
