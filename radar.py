"""Radar free LLM: snapshot ofert z sieci + diff + nowości.

Źródła (bez kluczy, zwykły GET):
- README awesome-freellm-apis (tabele providerów, markery BEGIN_X/END_X)
- freellm.net/models/?free=1 (tabela modeli, server-rendered HTML)

Auto-check raz dziennie przy starcie apki (patrz refresh_if_stale) + ręczny guzik.
Bezpieczniki: brak masowych alertów przy zmianie formatu / masowych zniknięciach.
"""

import re
from datetime import datetime
from html.parser import HTMLParser

import requests

from database import get_db_connection

README_URL = ("https://raw.githubusercontent.com/open-free-llm-api/"
              "awesome-freellm-apis/main/README.md")
MODELS_URL = "https://freellm.net/models/?free=1"
UA = {"User-Agent": "VibeCenter-Radar/1.0"}

MIN_PROVIDERS = 10   # parsowanie poniżej tego = zmiana formatu, nie zapisuj
MIN_MODELS = 50

DDL = """
CREATE TABLE IF NOT EXISTS radar_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS radar_providers (
    name TEXT PRIMARY KEY,
    free_models INTEGER NOT NULL DEFAULT 0,
    cc TEXT NOT NULL DEFAULT '',
    max_context TEXT NOT NULL DEFAULT '',
    key_url TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL DEFAULT '',
    last_seen TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS radar_models (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    score TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    modality TEXT NOT NULL DEFAULT '',
    rate_limit TEXT NOT NULL DEFAULT '',
    released TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    model_url TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL DEFAULT '',
    last_seen TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (provider, model)
);
CREATE TABLE IF NOT EXISTS radar_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    seen INTEGER NOT NULL DEFAULT 0
);
"""


def ensure_tables():
    con = get_db_connection()
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _meta_get(key):
    ensure_tables()
    con = get_db_connection()
    try:
        r = con.execute("SELECT value FROM radar_meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else ""
    finally:
        con.close()


def _meta_set(key, value):
    con = get_db_connection()
    try:
        con.execute("INSERT INTO radar_meta (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value))
        con.commit()
    finally:
        con.close()


# ==================== parsowanie README ====================

def _parse_md_table(body):
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = [c.strip().lower() for c in lines[0].strip("|").split("|")]
    if not any("---" in c for c in lines[1].split("|")):
        return []
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def parse_readme(text):
    """{nazwa_sekcji: [wiersze]} dla każdego bloku BEGIN_X/END_X z tabelą."""
    out = {}
    for m in re.finditer(r"<!--\s*BEGIN_(\w+)\s*-->(.*?)<!--\s*END_\1\s*-->",
                         text or "", re.S):
        rows = _parse_md_table(m.group(2))
        if rows:
            out[m.group(1)] = rows
    return out


def _md_text(cell):
    m = re.match(r"\[(.*?)\]\(.*?\)\s*$", cell or "")
    return _ws(m.group(1) if m else (cell or ""))


def _md_href(cell):
    m = re.search(r'href="([^"]+)"', cell or "")
    if m:
        return m.group(1)
    m = re.search(r"\[.*?]\((.*?)\)", cell or "")
    return m.group(1) if m else ""


def _to_int(val):
    return int(re.sub(r"\D", "", val or "") or 0)


def providers_from_readme(parsed):
    """Wiersze providerów z sekcji zawierającej kolumnę 'provider'."""
    for section in ("PERMANENT_FREE", *parsed.keys()):
        rows = parsed.get(section) or []
        if rows and "provider" in rows[0]:
            out = []
            for r in rows:
                name = _md_text(r.get("provider", ""))
                if name:
                    out.append({
                        "name": name,
                        "free_models": _to_int(r.get("free models", "")),
                        "cc": _ws(r.get("credit card?", "")),
                        "max_context": _ws(r.get("max context", "")),
                        "key_url": _md_href(r.get("get api key", "")),
                    })
            if out:
                return out
    return []


# ==================== parsowanie strony modeli ====================

class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None
        self._cell_links = None
        self._in_th = False
        self._link_href = None
        self._link_text = None

    def handle_starttag(self, tag, attrs):
        if tag == "table" and self._table is None:
            self._table = {"headers": [], "rows": []}
        elif tag == "tr" and self._table is not None and self._row is None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None and self._cell is None:
            self._cell = []
            self._cell_links = []
            self._in_th = (tag == "th")
        elif tag == "a" and self._cell is not None and self._link_text is None:
            self._link_href = dict(attrs).get("href", "")
            self._link_text = []

    def handle_data(self, data):
        if self._link_text is not None:
            self._link_text.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._link_text is not None:
            self._cell_links.append((self._link_href, _ws("".join(self._link_text))))
            self._link_text = None
            self._link_href = None
        elif tag in ("td", "th") and self._cell is not None:
            text = _ws("".join(self._cell))
            if self._in_th:
                self._table["headers"].append(text.lower())
            else:
                self._row.append({"text": text, "links": self._cell_links})
            self._cell = None
            self._cell_links = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def parse_models_html(html):
    """Wiersze modeli z tabeli zawierającej kolumny provider + model."""
    try:
        p = _TableParser()
        p.feed(html or "")
    except Exception:
        return []
    for t in p.tables:
        cols = t["headers"]
        if "provider" not in cols or "model" not in cols:
            continue
        idx = {c: cols.index(c) for c in cols}
        out = []
        for r in t["rows"]:
            if len(r) < len(cols):
                continue
            pc, mc = r[idx["provider"]], r[idx["model"]]
            prov = (pc["links"][0][1] if pc["links"] else pc["text"]) or ""
            mod = (mc["links"][0][1] if mc["links"] else mc["text"]) or ""
            if not prov or not mod:
                continue
            def cell(name):
                return r[idx[name]]["text"] if name in idx else ""
            out.append({
                "provider": prov,
                "model": re.sub(r"\s*Verified\s*", "", mod).strip(),
                "score": cell("score"),
                "context": cell("context"),
                "modality": cell("modality"),
                "rate_limit": cell("rate limit"),
                "released": cell("released"),
                "status": cell("status"),
                "verified": 1 if "verified" in mc["text"].lower() else 0,
                "model_url": mc["links"][0][0] if mc["links"] else "",
            })
        if out:
            return out
    return []


# ==================== snapshot + diff ====================

def _add_news(con, now, kind, title, detail=""):
    con.execute("INSERT INTO radar_news (created_at, kind, title, detail, seen)"
                " VALUES (?, ?, ?, ?, 0)", (now, kind, title, detail))


def _sync_providers(rows, now):
    ensure_tables()
    con = get_db_connection()
    try:
        existing = {r["name"]: dict(r)
                    for r in con.execute("SELECT * FROM radar_providers").fetchall()}
        if not existing:
            for p in rows:  # baseline — bez alertów
                con.execute("INSERT INTO radar_providers (name, free_models, cc, max_context,"
                            " key_url, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (p["name"], p["free_models"], p["cc"], p["max_context"],
                             p["key_url"], now, now))
            con.commit()
            return 0
        fresh = {p["name"]: p for p in rows}
        if existing and not fresh:
            raise ValueError("pusta lista providerów — przerwano (źródło padło?)")
        removed = [n for n in existing if n not in fresh]
        if len(removed) > max(5, len(existing) // 2):
            raise ValueError("podejrzanie dużo zniknięć providerów (%d) — przerwano" % len(removed))
        n = 0
        for name, p in fresh.items():
            if name not in existing:
                con.execute("INSERT INTO radar_providers (name, free_models, cc, max_context,"
                            " key_url, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (name, p["free_models"], p["cc"], p["max_context"],
                             p["key_url"], now, now))
                _add_news(con, now, "new_provider", "🆕 Nowy provider: %s" % name,
                          "%d modeli free · %s" % (p["free_models"], p["cc"] or "—"))
                n += 1
            else:
                old = existing[name]
                con.execute("UPDATE radar_providers SET free_models = ?, cc = ?, max_context = ?,"
                            " key_url = ?, last_seen = ? WHERE name = ?",
                            (p["free_models"], p["cc"], p["max_context"], p["key_url"], now, name))
                if p["free_models"] != old["free_models"]:
                    arrow = "📈" if p["free_models"] > old["free_models"] else "📉"
                    _add_news(con, now, "models_count",
                              "%s %s: %d → %d modeli" % (arrow, name, old["free_models"], p["free_models"]))
                    n += 1
        for name in removed:
            con.execute("DELETE FROM radar_providers WHERE name = ?", (name,))
            _add_news(con, now, "removed_provider", "⚠️ Zniknął z listy: %s" % name)
            n += 1
        con.commit()
        return n
    finally:
        con.close()


def _sync_models(rows, now):
    ensure_tables()
    con = get_db_connection()
    try:
        existing = {(r["provider"], r["model"]): dict(r)
                    for r in con.execute("SELECT * FROM radar_models").fetchall()}
        if not existing:
            for m in rows:  # baseline — bez alertów
                con.execute("INSERT INTO radar_models (provider, model, score, context, modality,"
                            " rate_limit, released, status, verified, model_url,"
                            " first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (m["provider"], m["model"], m["score"], m["context"], m["modality"],
                             m["rate_limit"], m["released"], m["status"], m["verified"],
                             m["model_url"], now, now))
            con.commit()
            return 0
        fresh = {(m["provider"], m["model"]): m for m in rows}
        if existing and not fresh:
            raise ValueError("pusta lista modeli — przerwano (źródło padło?)")
        removed = [k for k in existing if k not in fresh]
        if len(removed) > max(10, len(existing) // 5):
            raise ValueError("podejrzanie dużo zniknięć modeli (%d) — przerwano" % len(removed))
        n = 0
        for key, m in fresh.items():
            if key not in existing:
                con.execute("INSERT INTO radar_models (provider, model, score, context, modality,"
                            " rate_limit, released, status, verified, model_url,"
                            " first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (m["provider"], m["model"], m["score"], m["context"], m["modality"],
                             m["rate_limit"], m["released"], m["status"], m["verified"],
                             m["model_url"], now, now))
                _add_news(con, now, "new_model", "🆕 Nowy model: %s (%s)" % (m["model"], m["provider"]),
                          "score %s · %s" % (m["score"] or "—", m["rate_limit"] or "—"))
                n += 1
            else:
                old = existing[key]
                con.execute("UPDATE radar_models SET score = ?, context = ?, modality = ?,"
                            " rate_limit = ?, released = ?, status = ?, verified = ?,"
                            " model_url = ?, last_seen = ? WHERE provider = ? AND model = ?",
                            (m["score"], m["context"], m["modality"], m["rate_limit"],
                             m["released"], m["status"], m["verified"], m["model_url"],
                             now, m["provider"], m["model"]))
                if (m["status"] or "") != (old["status"] or ""):
                    _add_news(con, now, "status_change",
                              "🔄 %s (%s): %s → %s" % (m["model"], m["provider"],
                                                      old["status"] or "—", m["status"] or "—"))
                    n += 1
        for key in removed:
            con.execute("DELETE FROM radar_models WHERE provider = ? AND model = ?",
                        (key[0], key[1]))
            _add_news(con, now, "removed_model", "⚠️ Zniknął: %s (%s)" % (key[1], key[0]))
            n += 1
        con.commit()
        return n
    finally:
        con.close()


def _http(url):
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    if len(resp.content) > 5 * 1024 * 1024:
        raise ValueError("odpowiedź za duża (>5 MB)")
    return resp.text


def refresh(force=False):
    """Pobierz oba źródła, zrób diff. force omija strażnik 'raz dziennie'."""
    ensure_tables()
    if not force and _meta_get("last_fetch_date") == _today():
        return {"status": "skipped", "reason": "dzisiejsze dane już pobrane"}
    now = _now()
    summary = {"providers": 0, "models": 0, "news": 0, "errors": []}
    try:
        prows = providers_from_readme(parse_readme(_http(README_URL)))
        if len(prows) < MIN_PROVIDERS:
            raise ValueError("za mało providerów (%d) — format? nie zapisuję" % len(prows))
        summary["news"] += _sync_providers(prows, now)
        summary["providers"] = len(prows)
    except Exception as exc:
        summary["errors"].append("README: %s" % exc)
    try:
        mrows = parse_models_html(_http(MODELS_URL))
        if len(mrows) < MIN_MODELS:
            raise ValueError("za mało modeli (%d) — format? nie zapisuję" % len(mrows))
        summary["news"] += _sync_models(mrows, now)
        summary["models"] = len(mrows)
    except Exception as exc:
        summary["errors"].append("Modele: %s" % exc)
    _meta_set("last_fetch_date", _today())
    _meta_set("last_fetch_at", now)
    _meta_set("last_status", "ok" if not summary["errors"] else "; ".join(summary["errors"]))
    summary["status"] = "ok" if (summary["providers"] or summary["models"]) else "error"
    return summary


def refresh_if_stale():
    """Do lifespanu: tylko gdy dziś jeszcze nie sprawdzano."""
    ensure_tables()
    if _meta_get("last_fetch_date") == _today():
        return {"status": "skipped"}
    return refresh()


# ==================== odczyt ====================

def get_status():
    ensure_tables()
    con = get_db_connection()
    try:
        np_ = con.execute("SELECT COUNT(*) FROM radar_providers").fetchone()[0]
        nm = con.execute("SELECT COUNT(*) FROM radar_models").fetchone()[0]
    finally:
        con.close()
    return {
        "last_fetch_at": _meta_get("last_fetch_at"),
        "last_status": _meta_get("last_status"),
        "providers": np_,
        "models": nm,
        "unseen": get_unseen_count(),
    }


def get_unseen_count():
    ensure_tables()
    con = get_db_connection()
    try:
        return con.execute("SELECT COUNT(*) FROM radar_news WHERE seen = 0").fetchone()[0]
    finally:
        con.close()


def list_news(limit=100):
    ensure_tables()
    con = get_db_connection()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM radar_news ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    finally:
        con.close()


def mark_all_seen():
    ensure_tables()
    con = get_db_connection()
    try:
        cur = con.execute("UPDATE radar_news SET seen = 1 WHERE seen = 0")
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def list_providers():
    ensure_tables()
    con = get_db_connection()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM radar_providers ORDER BY free_models DESC, name").fetchall()]
    finally:
        con.close()


def list_models():
    ensure_tables()
    con = get_db_connection()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM radar_models").fetchall()]
    finally:
        con.close()
