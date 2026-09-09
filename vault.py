from database import get_db_connection


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * max(len(key) - 8, 4) + key[-4:]


def list_vault_keys(query: str | None = None):
    conn = get_db_connection()
    sql = "SELECT * FROM vault_keys WHERE 1=1"
    params = []
    if query:
        sql += " AND (service_name LIKE ? OR env_var LIKE ? OR tags LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])
    sql += " ORDER BY service_name COLLATE NOCASE"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_vault_key(key_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM vault_keys WHERE id = ?", (key_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_vault_key(service_name: str, env_var: str, api_key: str, tags: str = "", is_primary: bool = False):
    conn = get_db_connection()
    if is_primary:
        conn.execute("UPDATE vault_keys SET is_primary = 0 WHERE service_name = ?", (service_name.strip(),))
    cur = conn.execute(
        "INSERT INTO vault_keys (service_name, env_var, api_key, tags, is_primary) VALUES (?, ?, ?, ?, ?)",
        (service_name.strip(), env_var.strip(), api_key.strip(), tags.strip(), 1 if is_primary else 0),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_vault_key(new_id)


def update_vault_key(key_id: int, service_name: str, env_var: str, api_key: str | None, tags: str, is_primary: bool):
    conn = get_db_connection()
    existing = conn.execute("SELECT api_key FROM vault_keys WHERE id = ?", (key_id,)).fetchone()
    if not existing:
        conn.close()
        return None
    new_key = api_key.strip() if api_key and api_key.strip() else existing["api_key"]
    if is_primary:
        conn.execute("UPDATE vault_keys SET is_primary = 0 WHERE service_name = ? AND id != ?", (service_name.strip(), key_id))
    conn.execute(
        "UPDATE vault_keys SET service_name = ?, env_var = ?, api_key = ?, tags = ?, is_primary = ? WHERE id = ?",
        (service_name.strip(), env_var.strip(), new_key, tags.strip(), 1 if is_primary else 0, key_id),
    )
    conn.commit()
    conn.close()
    return get_vault_key(key_id)


def delete_vault_key(key_id: int) -> None:
    conn = get_db_connection()
    conn.execute("DELETE FROM vault_keys WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()


def touch_last_used(key_id: int) -> None:
    conn = get_db_connection()
    conn.execute("UPDATE vault_keys SET last_used_at = datetime('now') WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()


def get_primary_key_for_service(service_name: str) -> str:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM vault_keys WHERE service_name = ? ORDER BY is_primary DESC, id ASC LIMIT 1",
        (service_name,),
    ).fetchone()
    conn.close()
    if not row:
        return ""
    touch_last_used(row["id"])
    return row["api_key"]


def export_env_text() -> str:
    conn = get_db_connection()
    rows = conn.execute("SELECT env_var, api_key FROM vault_keys ORDER BY service_name COLLATE NOCASE").fetchall()
    conn.close()
    lines = [f'{r["env_var"]}={r["api_key"]}' for r in rows]
    return "\n".join(lines) + ("\n" if lines else "")