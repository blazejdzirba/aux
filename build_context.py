#!/usr/bin/env python3
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

# Rozszerzenia, które chcemy uwzględnić w outputcie
INCLUDE_EXTS = {
    ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yml", ".yaml",
    ".html", ".css", ".js", ".ts", ".json", ".sql", ".sh", ".pdf",
}
# Domyślne katalogi do ignorowania (rozszerzone o specyficzne dla tego projektu)
IGNORE_DIRS = {
    "venv", ".venv", "env", "__pycache__", ".git", ".hg", ".svn",
    "node_modules", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox", "dist", "build", "out", "target", "coverage",
    "htmlcov", ".next", ".nuxt", ".eggs", "blueprints",
    "data",                     # duże pliki danych i bazy, nie potrzebne w kontekście kodu
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
        # filtrujemy katalogi
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".")
            and d not in IGNORE_DIRS
            and not d.endswith(".egg-info")
        )
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
    """Kolejność: najpierw .py, potem .html/.css/.js, potem .md/.txt, na resztę."""
    low = rel.lower()
    if low.endswith(".py"):
        grp = 0
    elif any(low.endswith(ext) for ext in (".html", ".css", ".js")):
        grp = 1
    elif any(low.endswith(ext) for ext in (".md", ".txt")):
        grp = 2
    else:
        grp = 3
    return (grp, rel)

def build(pack):
    chunks = []
    total = 0
    for rel in pack:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            text = f"<nie odczytano: {exc}>"
        block = (
            "# " + "=" * 68 + "\n"
            f"# PLIK: {rel} ({len(text)} znaków)\n"
            "# " + "=" * 68 + "\n"
            + text
            + "\n"
        )
        chunks.append(block)
        total += len(block)
    toc = "\n".join("- " + r for r in pack)
    header = (
        f"# Blueprint projektu: {ROOT.name}\n"
        f"# Plików: {len(pack)}, znaków: {total}, ~tokenów: {total // 4}\n\n"
        f"## Spis plików\n{toc}\n\n"
    )
    return header + "\n".join(chunks), total

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
        print(
            f"OK: {MAIN_OUT} ({len(files)} plików, {total} znaków, ~{total // 4} tokenów)"
        )
        return
    # podział na części, jeśli przekroczono limit znaków
    parts, cur, cur_len = [], [], 0
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        block_len = len(text) + 200  # dodatkowy narzut nagłówka
        if cur and cur_len + block_len > MAX_CHARS:
            parts.append(cur)
            cur, cur_len = [], 0
        cur.append(rel)
        cur_len += block_len
    if cur:
        parts.append(cur)
    for i, pack in enumerate(parts, 1):
        body, n = build(pack)
        out = OUT_DIR / f"full_app_part{i}.md"
        out.write_text(body, encoding="utf-8")
        print(f"OK: {out} ({len(pack)} plików, {n} znaków)")
    print(f"Podzielono na {len(parts)} części (limit {MAX_CHARS} znaków).")

if __name__ == "__main__":
    main()