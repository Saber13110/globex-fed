"""Client HTTP vers Jarvis-OS (sidecar)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class JarvisBridgeError(Exception):
    """Erreur de communication avec Jarvis."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = (settings.jarvis_api_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _base(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return s.jarvis_base_url.rstrip("/")


def check_jarvis_health(settings: Settings | None = None) -> dict[str, Any]:
    """Ping GET /api/health sur Jarvis."""
    s = settings or get_settings()
    if not s.jarvis_enabled:
        return {"online": False, "detail": "Jarvis désactivé (JARVIS_ENABLED=false)", "latency_ms": None}

    url = f"{_base(s)}/api/health"
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=min(10.0, s.jarvis_timeout_seconds)) as client:
            resp = client.get(url, headers=_headers(s))
            latency = round((time.perf_counter() - started) * 1000, 1)
            if resp.status_code >= 400:
                return {
                    "online": False,
                    "detail": f"HTTP {resp.status_code}",
                    "latency_ms": latency,
                }
            return {"online": True, "detail": "ok", "latency_ms": latency}
    except httpx.TimeoutException:
        return {"online": False, "detail": "timeout", "latency_ms": None}
    except httpx.RequestError as exc:
        logger.warning("Jarvis health check failed: %s", exc)
        return {"online": False, "detail": str(exc), "latency_ms": None}


def call_jarvis_generate(
    message: str,
    *,
    jarvis_session_id: str | None = None,
    settings: Settings | None = None,
) -> tuple[str, str | None, float]:
    """
    Appelle POST /api/voice/generate (stream agrégé côté client httpx).
    Retourne (reply_text, jarvis_session_id, latency_ms).
    """
    s = settings or get_settings()
    if not s.jarvis_enabled:
        raise JarvisBridgeError("Jarvis est désactivé sur ce serveur FedEx.")

    url = f"{_base(s)}/api/voice/generate"
    payload = {"message": message, "session_id": jarvis_session_id}
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=s.jarvis_timeout_seconds) as client:
            resp = client.post(url, json=payload, headers=_headers(s))
            latency = round((time.perf_counter() - started) * 1000, 1)
            if resp.status_code >= 400:
                detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                raise JarvisBridgeError(detail, status_code=resp.status_code)
            reply = (resp.text or "").strip()
            if not reply:
                raise JarvisBridgeError("Réponse Jarvis vide — vérifiez qu'Ollama tourne.")
            new_sid = resp.headers.get("X-Session-Id") or jarvis_session_id
            return reply, new_sid, latency
    except JarvisBridgeError:
        raise
    except httpx.TimeoutException as exc:
        raise JarvisBridgeError(
            f"Jarvis n'a pas répondu dans les {int(s.jarvis_timeout_seconds)} s — Ollama peut être en cold start."
        ) from exc
    except httpx.RequestError as exc:
        raise JarvisBridgeError(
            f"Impossible de joindre Jarvis sur {_base(s)} — lancez: python -m jarvis.app"
        ) from exc
