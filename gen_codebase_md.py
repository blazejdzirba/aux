#!/usr/bin/env python3
"""Generuje CODEBASE.md — cały kod AUX w jednym pliku .md ze ścieżkami."""
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
OUT = ROOT / "CODEBASE.md"

FILES = [
    "requirements.txt",
    ".gitignore",
    "config.py",
    "database.py",
    "main.py",
    "models.py",
    "routers/__init__.py",
    "routers/models_router.py",
    "routers/playground_router.py",
    "routers/documents_router.py",
    "routers/settings_router.py",
    "services/__init__.py",
    "services/omniroute_client.py",
    "services/model_monitor.py",
    "services/prompt_optimizer.py",
    "templates/base.html",
    "templates/models_list.html",
    "templates/playground.html",
    "templates/documents.html",
    "templates/settings.html",
    "templates/partials/model_row.html",
    "templates/partials/playground_result.html",
    "templates/partials/optimizer_result.html",
    "templates/partials/document_item.html",
    "templates/partials/document_editor.html",
    "static/app.css",
    "test_final.sh",
]

LANG = {".py": "python", ".html": "html", ".css": "css", ".sh": "bash",
        ".txt": "text", ".md": "markdown"}

total = 0
parts = [
    "# AUX — kod źródłowy",
    "",
    f"Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    f"Repozytorium: `/home/blaise/Projekty/01_AUX/aux/` (branch main)",
    "",
    "## Spis plików",
    "",
]

bodies = []
for rel in FILES:
    p = ROOT / rel
    if not p.exists():
        parts.append(f"- `{rel}` — **BRAK**")
        continue
    content = p.read_text(encoding="utf-8")
    lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
    if not content.strip():
        lines = 0
    total += lines
    ext = p.suffix or ""
    lang = LANG.get(ext, "")
    fence = f"```{lang}" if lang else "```"
    bodies.append(
        f"\n---\n\n## `{rel}` ({lines} linii)\n\n{fence}\n{content.rstrip()}\n```\n"
    )
    parts.append(f"- `{rel}` — {lines} linii")

parts.append(f"\n**Razem: {total} linii w {len(FILES)} plikach**\n")
parts.extend(bodies)
OUT.write_text("\n".join(parts), encoding="utf-8")
print(f"OK: {OUT} ({OUT.stat().st_size} bajtów, {total} linii kodu)")
