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
