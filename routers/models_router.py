from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from models import list_ai_models, get_model, update_model_status, delete_model
from services.model_monitor import check_single_model

router = APIRouter(prefix="/models", tags=["models"])
templates = Jinja2Templates(directory="templates")

@router.get("", response_class=HTMLResponse)
async def models_list(request: Request):
    models = list_ai_models()
    return templates.TemplateResponse(request, "models_list.html", {"models": models, "active_page": "models"})

@router.post("/{model_id}/test", response_class=HTMLResponse)
async def test_model(request: Request, model_id: int):
    await check_single_model(model_id)
    model = get_model(model_id)
    return templates.TemplateResponse(request, "partials/model_row.html", {"m": model})

@router.post("/{model_id}/delete", response_class=HTMLResponse)
async def remove_model(model_id: int):
    delete_model(model_id)
    return RedirectResponse("/models", status_code=303)
