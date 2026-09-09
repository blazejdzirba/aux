from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from models import list_ai_models, get_model
from services.omniroute_client import run_prompt
from services.prompt_optimizer import optimize_prompt, create_system_prompt, generate_questions

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/playground", response_class=HTMLResponse)
async def playground_view(request: Request):
    models = list_ai_models()
    return templates.TemplateResponse(request, "playground.html", {"models": models, "active_page": "playground"})

@router.post("/playground/run", response_class=HTMLResponse)
async def playground_run(request: Request, model_id: int = Form(...), prompt: str = Form(...)):
    model = get_model(model_id)
    try:
        result = run_prompt(model["model_id"], prompt)
    except Exception as e:
        result = {"status": "error", "text": "", "latency_ms": None, "error": str(e)}
    return templates.TemplateResponse(request, "partials/playground_result.html", {"result": result})

@router.post("/prompt-optimizer/optimize", response_class=HTMLResponse)
async def optimizer_run(request: Request, prompt: str = Form(...), mode: str = Form("standard")):
    try:
        if mode == "systemowy":
            result = create_system_prompt(prompt)
        elif mode == "mega":
            result = generate_questions(prompt)
        else:
            result = optimize_prompt(prompt)
        return templates.TemplateResponse(request, "partials/optimizer_result.html", {"result": result})
    except Exception as e:
        return templates.TemplateResponse(request, "partials/optimizer_result.html", {"error": str(e)})
