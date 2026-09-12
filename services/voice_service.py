"""Transkrypcja głosowa dla dyktafonu AUX (opcja B).

Kolejność silników:
1) Gateway OmniRoute (OpenAI-compatible POST /audio/transcriptions) — zero nowych zależności.
2) Lokalny faster-whisper (CPU, model base) — fallback, wymaga `pip install faster-whisper`.
"""
import os
import tempfile

import requests

from config import get_omniroute_api_key, get_omniroute_base

WHISPER_MODEL = "whisper-1"   # model dla gatewaya (standard OpenAI)
LOCAL_MODEL = "base"          # model faster-whisper (jak desktopowy skrypt)
GATEWAY_TIMEOUT = 180


class VoiceError(RuntimeError):
    """Błąd do pokazania użytkownikowi w okienku dyktafonu."""


class _GatewayUnsupported(Exception):
    """Gateway nie ma endpointu audio — sygnał do próby lokalnego Whispera."""


def _transcribe_gateway(audio_bytes: bytes, filename: str, language: str = "pl") -> str:
    key = get_omniroute_api_key()
    if not key:
        raise VoiceError("Brak klucza API (Vault 'omniroute' lub Ustawienia).")
    url = get_omniroute_base().rstrip("/") + "/audio/transcriptions"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": "Bearer %s" % key},
            files={"file": (filename, audio_bytes, "audio/webm")},
            data={"model": WHISPER_MODEL, "language": language or "pl", "response_format": "json"},
            timeout=GATEWAY_TIMEOUT,
        )
    except requests.Timeout:
        raise VoiceError("Gateway nie odpowiedział w czasie (%d s)." % GATEWAY_TIMEOUT)
    except requests.RequestException as e:
        raise VoiceError("Błąd połączenia z gatewayem: %s" % e)
    if resp.status_code in (404, 405, 501):
        raise _GatewayUnsupported("gateway HTTP %d" % resp.status_code)
    if resp.status_code != 200:
        raise VoiceError("Gateway: HTTP %d: %s" % (resp.status_code, resp.text[:300]))
    try:
        text = resp.json().get("text", "")
    except Exception:
        raise VoiceError("Nieoczekiwana odpowiedź gatewaya.")
    if not text.strip():
        raise VoiceError("Gateway zwrócił pustą transkrypcję.")
    return text.strip()


_local_model = None


def local_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        # CPU + int8: działa wszędzie, bez problemów z fp16 na kartach NVIDIA.
        # Pierwsze wywołanie ściąga model (~150 MB) — wymaga wtedy internetu.
        _local_model = WhisperModel(LOCAL_MODEL, device="cpu", compute_type="int8")
    return _local_model


def _transcribe_local(audio_bytes: bytes, filename: str, language: str = "pl") -> str:
    if not local_available():
        raise VoiceError("brak lokalnego Whisper (zainstaluj: pip install faster-whisper)")
    suffix = os.path.splitext(filename or "")[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(audio_bytes)
        tmp.close()
        model = _get_local_model()
        segments, _info = model.transcribe(tmp.name, language=language or "pl")
        text = "".join(s.text for s in segments).strip()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    if not text:
        raise VoiceError("Lokalny Whisper zwrócił pustą transkrypcję.")
    return text


def transcribe(audio_bytes: bytes, filename: str = "nagranie.webm",
               language: str = "pl") -> tuple[str, str]:
    """Transkrybuje nagranie. Zwraca (tekst, silnik: 'gateway' | 'lokalny Whisper')."""
    if not audio_bytes:
        raise VoiceError("Pusty plik audio.")
    try:
        return _transcribe_gateway(audio_bytes, filename, language), "gateway"
    except _GatewayUnsupported as e:
        try:
            return _transcribe_local(audio_bytes, filename, language), "lokalny Whisper"
        except VoiceError as le:
            raise VoiceError("Gateway nie obsługuje transkrypcji (%s); %s." % (e, le))


def voice_status() -> dict:
    return {
        "gateway_base": get_omniroute_base(),
        "has_key": bool(get_omniroute_api_key()),
        "local_whisper": local_available(),
        "local_model": LOCAL_MODEL,
        "gateway_model": WHISPER_MODEL,
    }
