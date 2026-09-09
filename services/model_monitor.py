from models import get_model, update_model_status
from services.omniroute_client import run_prompt

async def check_single_model(model_id: int):
    model = get_model(model_id)
    if not model:
        return
    try:
        result = run_prompt(model["model_id"], "Ping")
        status = result["status"]
        update_model_status(model_id, status, result.get("latency_ms"), result.get("error", ""))
    except Exception as e:
        update_model_status(model_id, "error", None, str(e))
