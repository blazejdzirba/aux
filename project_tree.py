"""Drzewo projektu + build_context.py (ekstrakt kodu do blueprintu).

- Żywe drzewo katalogu: próbuje systemowego `tree` (subprocess, timeout),
  fallback to własny renderer (os.scandir) — zero zależności.
- Ścieżka roota w tabeli project_roots (główna baza przez database.get_db_connection).
- BUILD_CONTEXT_TEMPLATE: samodzielny skrypt (tylko stdlib) do pobrania do roota
  projektu; po odpaleniu tworzy blueprints/full_app.md.
"""

import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import requests

from database import get_db_connection

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS project_roots (
    project_id INTEGER PRIMARY KEY,
    root_path TEXT NOT NULL DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
)
"""

# Katalogi narzędziowe pomijane w drzewie i statystykach.
IGNORE_DIRS = {
    "venv", ".venv", "env", "__pycache__", ".git", ".hg", ".svn",
    "node_modules", ".cache", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".nox", ".eggs",
    "dist", "build", "out", "target", "coverage", "htmlcov",
    ".next", ".nuxt", ".output", ".parcel-cache", ".turbo",
    ".svelte-kit", ".vite", ".vercel", ".serverless",
}
IGNORE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".so", ".o", ".a", ".log", ".tmp", ".swp"}
IGNORE_FILES = {".DS_Store", "Thumbs.db"}

TREE_IGNORE_PATTERN = "|".join(sorted(IGNORE_DIRS)) + "|*.pyc|*.pyo|*.log|.env*"

MAX_TREE_DEPTH = 5
MAX_TREE_LINES = 3000
MAX_WALK_ENTRIES = 50000
MAX_BLUEPRINT_CHARS = 500000
BLUEPRINT_PREVIEW_CHARS = 30000

FORBIDDEN_PREFIXES = ("/proc", "/sys", "/dev")


def ensure_table():
    con = get_db_connection()
    try:
        con.execute(TABLE_DDL)
        con.commit()
    finally:
        con.close()


def get_root(project_id):
    ensure_table()
    con = get_db_connection()
    try:
        r = con.execute("SELECT root_path FROM project_roots WHERE project_id = ?",
                        (project_id,)).fetchone()
        return r["root_path"] if r else ""
    finally:
        con.close()


def set_root(project_id, raw_path):
    """Zapisz root. Zwraca (ok: bool, komunikat)."""
    ensure_table()
    p = (raw_path or "").strip()
    if not p:
        return False, "Podaj ścieżkę do katalogu projektu."
    try:
        rp = str(Path(p).expanduser().resolve())
    except Exception:
        return False, "Nieprawidłowa ścieżka."
    if not os.path.isdir(rp):
        return False, "Katalog nie istnieje: " + rp
    if len(Path(rp).parts) <= 2:
        return False, "Za płytka ścieżka (ochrona przed / i /home) — wskaż katalog projektu."
    if any(rp == f or rp.startswith(f + "/") for f in FORBIDDEN_PREFIXES):
        return False, "Ścieżka systemowa jest zabroniona."
    con = get_db_connection()
    try:
        con.execute(
            "INSERT INTO project_roots (project_id, root_path, updated_at)"
            " VALUES (?, ?, datetime('now'))"
            " ON CONFLICT(project_id) DO UPDATE SET"
            " root_path = excluded.root_path, updated_at = datetime('now')",
            (project_id, rp),
        )
        con.commit()
    finally:
        con.close()
    return True, "Zapisano: " + rp


def _ignored_dir(name):
    return name.startswith(".") or name in IGNORE_DIRS or name.endswith(".egg-info")


def _ignored_file(name):
    if name.startswith(".") or name in IGNORE_FILES:
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    _, dot, suffix = name.rpartition(".")
    return bool(dot) and ("." + suffix.lower()) in IGNORE_SUFFIXES


def get_tree_text(root):
    """Zwraca dict(text, source, truncated)."""
    exe = shutil.which("tree")
    if exe:
        try:
            proc = subprocess.run(
                [exe, "-L", str(MAX_TREE_DEPTH), "--dirsfirst",
                 "-I", TREE_IGNORE_PATTERN, root],
                capture_output=True, text=True, errors="replace", timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return _cap_tree(proc.stdout, "tree")
        except (OSError, subprocess.SubprocessError):
            pass
    return _cap_tree(_render_tree_python(root), "python")


def _cap_tree(text, source):
    lines = text.splitlines()
    if len(lines) > MAX_TREE_LINES:
        text = "\n".join(lines[:MAX_TREE_LINES]) + (
            f"\n… (obcięto, pełne drzewo ma {len(lines)} linii)")
        return {"text": text, "source": source, "truncated": True}
    return {"text": text, "source": source, "truncated": False}


def _render_tree_python(root):
    out = [root]

    def walk(dirpath, prefix, depth, budget):
        if depth > MAX_TREE_DEPTH or budget[0] <= 0:
            return
        try:
            entries = sorted(os.scandir(dirpath),
                             key=lambda e: (not e.is_dir(follow_symlinks=False),
                                            e.name.lower()))
        except OSError:
            out.append(prefix + "… (brak dostępu)")
            budget[0] -= 1
            return
        items = [e for e in entries
                 if not (_ignored_dir(e.name) if e.is_dir(follow_symlinks=False)
                         else _ignored_file(e.name))]
        for i, e in enumerate(items):
            if budget[0] <= 0:
                out.append(prefix + "… (limit linii)")
                return
            last = i == len(items) - 1
            is_dir = e.is_dir(follow_symlinks=False)
            out.append(prefix + ("└── " if last else "├── ") + e.name + ("/" if is_dir else ""))
            budget[0] -= 1
            if is_dir:
                walk(e.path, prefix + ("    " if last else "│   "), depth + 1, budget)

    walk(root, "", 1, [MAX_TREE_LINES])
    return "\n".join(out)


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def get_stats(root):
    """Spacer po plikach: liczba, rozmiar, top rozszerzeń. Z limitami."""
    files = 0
    size = 0
    exts = Counter()
    seen = 0
    capped = False
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _ignored_dir(d)]
        for fn in filenames:
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                capped = True
                break
            if _ignored_file(fn):
                continue
            files += 1
            try:
                size += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
            _, dot, suffix = fn.rpartition(".")
            exts["." + suffix.lower() if dot else "(bez rozszerzenia)"] += 1
        if capped:
            break
    return {
        "files": files,
        "size": size,
        "size_h": _human(size),
        "exts": exts.most_common(10),
        "capped": capped,
    }


_TIK = None
_TIK_OK = None


def _encoder():
    global _TIK, _TIK_OK
    if _TIK_OK is None:
        try:
            import tiktoken
            _TIK = tiktoken.get_encoding("cl100k_base")
            _TIK_OK = True
        except Exception:
            _TIK_OK = False
    return _TIK if _TIK_OK else None


def estimate_tokens(text):
    enc = _encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return int(round(len(text) / 4))


def get_blueprint(root):
    """Pliki blueprints/*.md + podgląd głównego + tokeny."""
    bp_dir = os.path.join(root, "blueprints")
    files = []
    if os.path.isdir(bp_dir):
        try:
            names = sorted(os.listdir(bp_dir))
        except OSError:
            names = []
        for fn in names:
            if fn.endswith(".md"):
                try:
                    sz = os.path.getsize(os.path.join(bp_dir, fn))
                    files.append({"name": fn, "size": sz, "size_h": _human(sz)})
                except OSError:
                    pass
    content = ""
    cut = False
    main = os.path.join(bp_dir, "full_app.md")
    if os.path.isfile(main):
        try:
            with open(main, encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_BLUEPRINT_CHARS + 1)
            if len(content) > MAX_BLUEPRINT_CHARS:
                content = content[:MAX_BLUEPRINT_CHARS]
                cut = True
        except OSError:
            content = ""
    tokens = estimate_tokens(content) if content else 0
    return {
        "files": files,
        "exists": bool(content),
        "preview": content[:BLUEPRINT_PREVIEW_CHARS],
        "preview_cut": cut or len(content) > BLUEPRINT_PREVIEW_CHARS,
        "chars": len(content),
        "tokens": tokens,
        "estimated": _TIK_OK is not True,
    }


def read_blueprint_file(root, name):
    """Pełna treść wskazanego pliku z blueprints/ (nazwa zabezpieczona)."""
    if not name or "/" in name or "\\" in name or name.startswith(".") \
            or not name.endswith(".md") or not root:
        return None
    fp = os.path.join(root, "blueprints", name)
    if not os.path.isfile(fp):
        return None
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.read(MAX_BLUEPRINT_CHARS + 1)
    except OSError:
        return None


def describe(root):
    """Pełny pakiet dla zakładki: drzewo + statystyki + blueprint."""
    return {
        "tree": get_tree_text(root),
        "stats": get_stats(root),
        "blueprint": get_blueprint(root),
    }


BUILD_CONTEXT_TEMPLATE = '''#!/usr/bin/env python3
"""build_context.py — ekstrakt kodu projektu do blueprints/full_app.md.

Użycie: skopiuj do katalogu głównego projektu i odpal:
    python3 build_context.py
Opcjonalnie utwórz .contextignore (proste wzorce fnmatch, # to komentarz).
Tylko biblioteka standardowa — zero zależności.
"""

import fnmatch
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "blueprints"
MAIN_OUT = OUT_DIR / "full_app.md"
MAX_CHARS = 150_000  # powyżej -> podział na części

INCLUDE_EXTS = {
    ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yml", ".yaml",
    ".html", ".css", ".js", ".ts", ".json", ".sql", ".sh",
}
IGNORE_DIRS = {
    "venv", ".venv", "env", "__pycache__", ".git", ".hg", ".svn",
    "node_modules", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox", "dist", "build", "out", "target", "coverage",
    "htmlcov", ".next", ".nuxt", ".eggs", "blueprints",
}
IGNORE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".so", ".o", ".a", ".log", ".tmp"}


def load_contextignore():
    pats = []
    f = ROOT / ".contextignore"
    if f.is_file():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    return pats


def ignored_by_user(rel_posix, pats):
    for p in pats:
        if fnmatch.fnmatch(rel_posix, p):
            return True
        if fnmatch.fnmatch(rel_posix, p.rstrip("/") + "/*"):
            return True
    return False


def is_secret(name):
    return name == ".env" or name.startswith(".env.")


def collect(pats):
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".")
                             and d not in IGNORE_DIRS
                             and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            if fn.startswith(".") or is_secret(fn):
                continue
            ext = Path(fn).suffix.lower()
            if ext not in INCLUDE_EXTS or ext in IGNORE_SUFFIXES:
                continue
            rel = (Path(dirpath) / fn).relative_to(ROOT).as_posix()
            if ignored_by_user(rel, pats):
                continue
            found.append(rel)
    return found


def order_key(rel):
    low = rel.lower()
    if low.startswith("readme") or low.startswith("docs/") \\
            or "architecture" in low or low.startswith("context"):
        group = 0
    elif low.endswith(".py"):
        group = 1
    elif low.endswith((".md", ".txt")):
        group = 2
    else:
        group = 3
    return (group, rel)


def build(pack):
    chunks = []
    total = 0
    for rel in pack:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            text = "<nie odczytano: %s>" % exc
        block = "# " + "=" * 68 + "\\n# PLIK: %s (%d znaków)\\n# " % (rel, len(text)) \\
            + "=" * 68 + "\\n" + text + "\\n"
        chunks.append(block)
        total += len(block)
    toc = "\\n".join("- " + r for r in pack)
    header = (("# Blueprint projektu: %s\\n# Plików: %d, znaków: %d, ~tokenów: %d\\n\\n"
               "## Spis plików\\n%s\\n\\n")
              % (ROOT.name, len(pack), total, total // 4, toc))
    return header + "\\n".join(chunks), total


def main():
    pats = load_contextignore()
    files = sorted(collect(pats), key=order_key)
    if not files:
        print("Brak plików do ekstraktu (sprawdź rozszerzenia i .contextignore).")
        return
    OUT_DIR.mkdir(exist_ok=True)
    body, total = build(files)
    if total <= MAX_CHARS:
        MAIN_OUT.write_text(body, encoding="utf-8")
        print("OK: %s (%d plików, %d znaków, ~%d tokenów)"
              % (MAIN_OUT, len(files), total, total // 4))
        return
    parts, cur, cur_len = [], [], 0
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        block_len = len(text) + 200
        if cur and cur_len + block_len > MAX_CHARS:
            parts.append(cur)
            cur, cur_len = [], 0
        cur.append(rel)
        cur_len += block_len
    if cur:
        parts.append(cur)
    for i, pack in enumerate(parts, 1):
        body, n = build(pack)
        out = OUT_DIR / ("full_app_part%d.md" % i)
        out.write_text(body, encoding="utf-8")
        print("OK: %s (%d plików, %d znaków)" % (out, len(pack), n))
    print("Podzielono na %d części (limit %d znaków)." % (len(parts), MAX_CHARS))


if __name__ == "__main__":
    main()
'''

TUNE_SYSTEM = (
    "Jesteś programistą Pythona. Dostaniesz: (1) drzewo katalogu projektu, "
    "(2) statystyki plików, (3) gotowy skrypt build_context.py (tylko stdlib), który ekstrahuje kod projektu do blueprints/full_app.md. "
    "Zadanie: DOSTOSUJ skrypt do tego projektu — rozszerzenia, kolejność plików, dodatkowe ignorowane katalogi. "
    "Odpowiedz WYŁĄCZNIE kompletnym kodem Pythona w bloku ```python — żadnych wyjaśnień poza kodem. "
    "Skrypt musi pozostać samodzielny (tylko biblioteka standardowa), zachować obsługę .contextignore, "
    "wykluczać katalog blueprints oraz NIGDY nie dołączać plików .env ani sekretów."
)


def _extract_code(text):
    import re
    m = re.search(r"```python\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    return (text or "").strip()


def tune_script(tree_text, stats, model_id, key, base):
    """Wyślij szablon do modelu; zwróć (ok, skrypt_lub_błąd)."""
    exts = ", ".join("%s×%d" % (e, c) for e, c in stats["exts"])
    user_msg = (
        "DRZEWO PROJEKTU:\n%s\n\n"
        "STATYSTYKI: %d plików, %s, top rozszerzeń: %s\n\n"
        "SZABLON DO DOSTOSOWANIA:\n```python\n%s\n```"
        % (tree_text, stats["files"], stats["size_h"], exts, BUILD_CONTEXT_TEMPLATE)
    )
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": TUNE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 6000,
        "stream": False,
    }
    url = (base or "").rstrip("/") + "/chat/completions"
    try:
        resp = requests.post(url, headers={"Authorization": "Bearer %s" % key,
                                           "Content-Type": "application/json"},
                             json=payload, timeout=180)
    except requests.RequestException as exc:
        return False, "Błąd połączenia z gatewayem: %s" % exc
    if resp.status_code != 200:
        return False, "Gateway: HTTP %d: %s" % (resp.status_code, resp.text[:200])
    try:
        content = resp.json()["choices"][0]["message"]["content"] or ""
    except Exception:
        return False, "Nieoczekiwana odpowiedź gatewaya."
    script = _extract_code(content)
    if not script or len(script) < 200:
        return False, "Model nie zwrócił poprawnego skryptu."
    return True, script
