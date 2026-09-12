from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from database import get_db_connection

router = APIRouter(prefix="/prompts", tags=["prompts"])
templates = Jinja2Templates(directory="templates")


def _list_prompts():
    conn = get_db_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM saved_prompts ORDER BY created_at DESC"
    ).fetchall()]
    conn.close()
    return rows


@router.get("", response_class=HTMLResponse)
async def prompts_view(request: Request):
    return templates.TemplateResponse(
        request, "prompts.html",
        {"active_page": "prompts", "prompts": _list_prompts()},
    )


@router.post("/save", response_class=HTMLResponse)
async def save_prompt(request: Request, title: str = Form(...), content: str = Form(...),
                       source: str = Form("optimizer"), mode: str = Form("")):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO saved_prompts (title, content, source, mode) VALUES (?, ?, ?, ?)",
        (title.strip() or "Bez tytułu", content, source, mode),
    )
    conn.commit()
    conn.close()
    return templates.TemplateResponse(
        request, "partials/prompt_saved.html",
        {},
    )


@router.delete("/{prompt_id}", response_class=HTMLResponse)
async def delete_prompt(request: Request, prompt_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM saved_prompts WHERE id = ?", (prompt_id,))
    conn.commit()
    conn.close()
    return Response(status_code=200)
