from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from database import get_db_connection

router = APIRouter(prefix="/resources", tags=["resources"])
templates = Jinja2Templates(directory="templates")


def _fetchall(sql: str, params=()):
    conn = get_db_connection()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def _ctx(request: Request, tab: str = "links", **extra) -> dict:
    return {
        "request": request,
        "active_page": "resources",
        "active_tab": tab,
        "links": _fetchall("SELECT * FROM resource_links ORDER BY created_at DESC"),
        "notes": _fetchall("SELECT * FROM resource_notes ORDER BY updated_at DESC"),
        "tools": _fetchall("SELECT * FROM resource_tools ORDER BY name"),
        **extra,
    }


@router.get("", response_class=HTMLResponse)
async def resources_view(request: Request, tab: str = "links"):
    return templates.TemplateResponse(request, "resources.html", _ctx(request, tab=tab))


# ---------- Linki ----------
@router.post("/links", response_class=HTMLResponse)
async def link_create(request: Request, title: str = Form(...), url: str = Form(...),
                       category: str = Form(""), note: str = Form("")):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO resource_links (title, url, category, note) VALUES (?, ?, ?, ?)",
        (title.strip(), url.strip(), category.strip(), note.strip()),
    )
    conn.commit()
    conn.close()
    return templates.TemplateResponse(request, "partials/resource_links_list.html", _ctx(request, tab="links"))


@router.delete("/links/{link_id}", response_class=HTMLResponse)
async def link_delete(request: Request, link_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM resource_links WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()
    return Response(status_code=200)


# ---------- Notatki ----------
@router.post("/notes", response_class=HTMLResponse)
async def note_create(request: Request, title: str = Form(...), content: str = Form("")):
    conn = get_db_connection()
    conn.execute("INSERT INTO resource_notes (title, content) VALUES (?, ?)", (title.strip(), content))
    conn.commit()
    conn.close()
    return templates.TemplateResponse(request, "partials/resource_notes_list.html", _ctx(request, tab="notes"))


@router.put("/notes/{note_id}", response_class=HTMLResponse)
async def note_update(request: Request, note_id: int, title: str = Form(...), content: str = Form("")):
    conn = get_db_connection()
    conn.execute(
        "UPDATE resource_notes SET title = ?, content = ?, updated_at = datetime('now') WHERE id = ?",
        (title.strip(), content, note_id),
    )
    conn.commit()
    conn.close()
    return templates.TemplateResponse(request, "partials/resource_notes_list.html", _ctx(request, tab="notes"))


@router.delete("/notes/{note_id}", response_class=HTMLResponse)
async def note_delete(request: Request, note_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM resource_notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return Response(status_code=200)


# ---------- Narzędzia ----------
@router.post("/tools", response_class=HTMLResponse)
async def tool_create(request: Request, name: str = Form(...), url: str = Form(""),
                       description: str = Form(""), category: str = Form(""),
                       difficulty: str = Form(""), license: str = Form(""),
                       agent_friendly: str = Form("0")):
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO resource_tools (name, url, description, category, difficulty, license, agent_friendly)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name.strip(), url.strip(), description.strip(), category.strip(),
         difficulty.strip(), license.strip(), 1 if agent_friendly == "1" else 0),
    )
    conn.commit()
    conn.close()
    return templates.TemplateResponse(request, "partials/resource_tools_list.html", _ctx(request, tab="tools"))


@router.delete("/tools/{tool_id}", response_class=HTMLResponse)
async def tool_delete(request: Request, tool_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM resource_tools WHERE id = ?", (tool_id,))
    conn.commit()
    conn.close()
    return Response(status_code=200)
