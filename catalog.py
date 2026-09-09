from database import get_db_connection


def list_used_model_ids(provider_id: int) -> set[str]:
    conn = get_db_connection()
    rows = conn.execute("SELECT model_id FROM ai_models WHERE provider_id = ?", (provider_id,)).fetchall()
    conn.close()
    return {r["model_id"] for r in rows}


def list_ignored_model_ids() -> set[str]:
    conn = get_db_connection()
    rows = conn.execute("SELECT model_id FROM catalog_ignored").fetchall()
    conn.close()
    return {r["model_id"] for r in rows}


def ignore_models(model_ids: list[str]) -> None:
    if not model_ids:
        return
    conn = get_db_connection()
    conn.executemany("INSERT OR IGNORE INTO catalog_ignored (model_id) VALUES (?)", [(m,) for m in model_ids])
    conn.commit()
    conn.close()


def unignore_all() -> None:
    conn = get_db_connection()
    conn.execute("DELETE FROM catalog_ignored")
    conn.commit()
    conn.close()