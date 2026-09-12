"""Wyszukiwarka: katalog trybów szukania (nazwa + prompt systemowy + szablon zapytania).

Tryb = jedna "opcja wyszukiwania": szablon buduje zapytanie do GitHub API,
a prompt systemowy steruje agentem, który z wyników robi raport.
Własny plik bazy (finders.db w katalogu projektu) — główna baza nietknięta.
"""

import sqlite3
from datetime import datetime, timezone

DB_PATH = "finders.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS finders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    input_hint TEXT NOT NULL DEFAULT '',
    query_template TEXT NOT NULL DEFAULT '{q}',
    sort TEXT NOT NULL DEFAULT 'stars',
    system_prompt TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

SEEDS = [
    {
        "name": "Podobne projekty (GitHub)",
        "description": "Znajduje repozytoria podobne do opisanego projektu lub pomysłu.",
        "input_hint": "Np. 'markdown note taking app with sync' — po angielsku działa lepiej.",
        "query_template": "{q}",
        "sort": "stars",
        "system_prompt": (
            "Jesteś analitykiem open source. Użytkownik opisze projekt lub pomysł, "
            "a Ty dostaniesz listę repozytoriów znalezionych w GitHub API "
            "(format JSON: nazwa, link, opis, gwiazdki, język, data aktualizacji). "
            "Zadanie: wybierz 5–8 najbardziej trafnych pozycji i napisz raport PO POLSKU "
            "w formacie Markdown. Dla każdej pozycji: nazwa z linkiem, 1–2 zdania czym jest "
            "i dlaczego pasuje do opisu, liczba gwiazdek i język. "
            "Zasady: korzystaj WYŁĄCZNIE z podanej listy — nie wymyślaj repozytoriów ani linków. "
            "Jeśli nic nie pasuje, napisz to wprost i zaproponuj, jak doprecyzować opis. "
            "Bez wstępów i komentarzy meta — sam raport z krótkim podsumowaniem na końcu."
        ),
    },
    {
        "name": "Alternatywy open-source",
        "description": "Szuka darmowych zamienników płatnego programu na podstawie nazwy lub opisu.",
        "input_hint": "Np. 'Notion', 'Photoshop', 'alternative to Slack' — najlepiej nazwa po angielsku.",
        "query_template": "{q} alternative",
        "sort": "stars",
        "system_prompt": (
            "Jesteś ekspertem od oprogramowania open source. Użytkownik poda nazwę (płatnego) programu "
            "lub opis potrzeb, a Ty dostaniesz listę repozytoriów z GitHub API "
            "(JSON: nazwa, link, opis, gwiazdki, język, data aktualizacji). "
            "Zadanie: wskaż maks. 8 najlepszych OTWARTYCH alternatyw i napisz raport PO POLSKU w Markdown. "
            "Dla każdej: nazwa z linkiem, co zastępuje / do czego służy (1–2 zdania), kluczowe funkcje, gwiazdki. "
            "Licencję podawaj tylko jeśli wynika z opisu — nie zgaduj. "
            "Zasady: korzystaj WYŁĄCZNIE z podanej listy — zero wymyślonych projektów i linków. "
            "Jeśli wyniki są słabe, powiedz to i podpowiedz lepszą frazę (po angielsku). "
            "Na końcu krótki werdykt: 1–2 najmocniejsze typy."
        ),
    },
]

SORTS = ("stars", "updated")


def _connect(path=None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_db(path=None):
    """Utwórz tabelę i wsiej startowe tryby (raz, gdy pusto)."""
    con = _connect(path)
    try:
        con.execute(SCHEMA)
        n = con.execute("SELECT COUNT(*) FROM finders").fetchone()[0]
        if n == 0:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for s in SEEDS:
                con.execute(
                    "INSERT INTO finders (name, description, input_hint, query_template,"
                    " sort, system_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (s["name"], s["description"], s["input_hint"], s["query_template"],
                     s["sort"], s["system_prompt"], now),
                )
        con.commit()
    finally:
        con.close()


def list_finders(path=None):
    ensure_db(path)
    con = _connect(path)
    try:
        return [dict(r) for r in con.execute("SELECT * FROM finders ORDER BY id").fetchall()]
    finally:
        con.close()


def get_finder(fid, path=None):
    ensure_db(path)
    con = _connect(path)
    try:
        r = con.execute("SELECT * FROM finders WHERE id = ?", (fid,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def _clean(name, system_prompt, query_template, sort):
    name = (name or "").strip()
    system_prompt = (system_prompt or "").strip()
    if not name:
        raise ValueError("Nazwa trybu jest wymagana.")
    if not system_prompt:
        raise ValueError("Prompt systemowy jest wymagany.")
    query_template = (query_template or "").strip() or "{q}"
    if sort not in SORTS:
        sort = "stars"
    return name, system_prompt, query_template, sort


def add_finder(name, description="", input_hint="", query_template="{q}",
               sort="stars", system_prompt="", path=None):
    ensure_db(path)
    name, system_prompt, query_template, sort = _clean(name, system_prompt, query_template, sort)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con = _connect(path)
    try:
        try:
            cur = con.execute(
                "INSERT INTO finders (name, description, input_hint, query_template,"
                " sort, system_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, (description or "").strip(), (input_hint or "").strip(),
                 query_template, sort, system_prompt, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError("Tryb o tej nazwie już istnieje.")
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def update_finder(fid, name, description="", input_hint="", query_template="{q}",
                  sort="stars", system_prompt="", path=None):
    ensure_db(path)
    name, system_prompt, query_template, sort = _clean(name, system_prompt, query_template, sort)
    con = _connect(path)
    try:
        try:
            cur = con.execute(
                "UPDATE finders SET name = ?, description = ?, input_hint = ?,"
                " query_template = ?, sort = ?, system_prompt = ? WHERE id = ?",
                (name, (description or "").strip(), (input_hint or "").strip(),
                 query_template, sort, system_prompt, fid),
            )
        except sqlite3.IntegrityError:
            raise ValueError("Tryb o tej nazwie już istnieje.")
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def delete_finder(fid, path=None):
    ensure_db(path)
    con = _connect(path)
    try:
        cur = con.execute("DELETE FROM finders WHERE id = ?", (fid,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
