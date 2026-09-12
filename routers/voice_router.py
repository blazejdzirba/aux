from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from services.voice_service import transcribe, voice_status, VoiceError

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB (limit jak w OpenAI)


@router.get("/status")
async def status():
    try:
        return JSONResponse({"status": "ok", **voice_status()})
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)})


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), language: str = Form("pl")):
    try:
        data = await audio.read()
    except Exception as e:
        return JSONResponse({"status": "error", "text": "", "engine": "", "error": "Nie odczytano pliku: %s" % e})
    if len(data) > MAX_AUDIO_BYTES:
        return JSONResponse({"status": "error", "text": "", "engine": "", "error": "Nagranie za długie (limit 25 MB)."})
    try:
        text, engine = transcribe(data, audio.filename or "nagranie.webm", language)
    except VoiceError as e:
        return JSONResponse({"status": "error", "text": "", "engine": "", "error": str(e)})
    except Exception as e:
        return JSONResponse({"status": "error", "text": "", "engine": "", "error": str(e)})
    return JSONResponse({"status": "ok", "text": text, "engine": engine, "error": ""})
