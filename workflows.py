"""Workflow: statyczne ściągi procesów (kroki z promptami i szablonami dokumentów).

Tabele workflows + workflow_steps w GŁÓWNEJ bazie (przez database.get_db_connection).
database.py i models.py nietknięte — DDL robi ensure_tables().
"""

from database import get_db_connection

DDL = """
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS workflow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    template_name TEXT NOT NULL DEFAULT '',
    template_body TEXT NOT NULL DEFAULT ''
);
"""


def ensure_tables():
    con = get_db_connection()
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()


def list_workflows():
    ensure_tables()
    con = get_db_connection()
    try:
        return [dict(r) for r in con.execute(
            "SELECT w.*, (SELECT COUNT(*) FROM workflow_steps s WHERE s.workflow_id = w.id) AS steps"
            " FROM workflows w ORDER BY w.id").fetchall()]
    finally:
        con.close()


def get_workflow(wid):
    ensure_tables()
    con = get_db_connection()
    try:
        r = con.execute("SELECT * FROM workflows WHERE id = ?", (wid,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def list_steps(wid):
    ensure_tables()
    con = get_db_connection()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM workflow_steps WHERE workflow_id = ? ORDER BY position, id",
            (wid,)).fetchall()]
    finally:
        con.close()


def list_all():
    """Wszystko naraz dla strony (workflow + kroki)."""
    out = []
    for w in list_workflows():
        w["step_list"] = list_steps(w["id"])
        out.append(w)
    return out


def create_workflow(name, description=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Nazwa procesu jest wymagana.")
    ensure_tables()
    con = get_db_connection()
    try:
        cur = con.execute(
            "INSERT INTO workflows (name, description) VALUES (?, ?)",
            (name, (description or "").strip()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def update_workflow(wid, name, description=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Nazwa procesu jest wymagana.")
    ensure_tables()
    con = get_db_connection()
    try:
        cur = con.execute(
            "UPDATE workflows SET name = ?, description = ?, updated_at = datetime('now')"
            " WHERE id = ?",
            (name, (description or "").strip(), wid))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def delete_workflow(wid):
    ensure_tables()
    con = get_db_connection()
    try:
        con.execute("DELETE FROM workflow_steps WHERE workflow_id = ?", (wid,))
        cur = con.execute("DELETE FROM workflows WHERE id = ?", (wid,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def add_step(wid, title, instructions="", prompt="", template_name="", template_body=""):
    title = (title or "").strip()
    if not title:
        raise ValueError("Tytuł kroku jest wymagany.")
    if not get_workflow(wid):
        raise ValueError("Nie ma takiego procesu.")
    ensure_tables()
    con = get_db_connection()
    try:
        pos = con.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM workflow_steps"
                          " WHERE workflow_id = ?", (wid,)).fetchone()[0]
        cur = con.execute(
            "INSERT INTO workflow_steps (workflow_id, position, title, instructions,"
            " prompt, template_name, template_body) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (wid, pos, title, (instructions or "").strip(), prompt or "",
             (template_name or "").strip(), template_body or ""))
        con.execute("UPDATE workflows SET updated_at = datetime('now') WHERE id = ?", (wid,))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def update_step(sid, title, instructions="", prompt="", template_name="", template_body=""):
    title = (title or "").strip()
    if not title:
        raise ValueError("Tytuł kroku jest wymagany.")
    ensure_tables()
    con = get_db_connection()
    try:
        cur = con.execute(
            "UPDATE workflow_steps SET title = ?, instructions = ?, prompt = ?,"
            " template_name = ?, template_body = ? WHERE id = ?",
            (title, (instructions or "").strip(), prompt or "",
             (template_name or "").strip(), template_body or "", sid))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def delete_step(sid):
    ensure_tables()
    con = get_db_connection()
    try:
        r = con.execute("SELECT workflow_id, position FROM workflow_steps WHERE id = ?",
                        (sid,)).fetchone()
        if not r:
            return False
        con.execute("DELETE FROM workflow_steps WHERE id = ?", (sid,))
        con.execute("UPDATE workflow_steps SET position = position - 1"
                    " WHERE workflow_id = ? AND position > ?", (r["workflow_id"], r["position"]))
        con.commit()
        return True
    finally:
        con.close()


def move_step(sid, direction):
    """Przesuń krok w górę/dół (zamiana pozycji z sąsiadem). Zwraca False na krańcach."""
    ensure_tables()
    con = get_db_connection()
    try:
        r = con.execute("SELECT workflow_id, position FROM workflow_steps WHERE id = ?",
                        (sid,)).fetchone()
        if not r:
            return False
        delta = -1 if direction == "up" else 1
        other = con.execute(
            "SELECT id FROM workflow_steps WHERE workflow_id = ? AND position = ?",
            (r["workflow_id"], r["position"] + delta)).fetchone()
        if not other:
            return False
        con.execute("UPDATE workflow_steps SET position = ? WHERE id = ?",
                    (r["position"] + delta, sid))
        con.execute("UPDATE workflow_steps SET position = ? WHERE id = ?",
                    (r["position"], other["id"]))
        con.commit()
        return True
    finally:
        con.close()
