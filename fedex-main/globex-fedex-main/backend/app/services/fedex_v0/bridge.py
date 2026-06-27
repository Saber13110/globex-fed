"""Client HTTP vers fedex-v0 (sidecar)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class fedex-v0BridgeError(Exception):
    """Erreur de communication avec fedex-v0."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = (settings.fedex_v0_api_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _base(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return s.fedex_v0_base_url.rstrip("/")


def check_fedex_v0_health(settings: Settings | None = None) -> dict[str, Any]:
    """Ping GET /api/health sur fedex-v0."""
    s = settings or get_settings()
    if not s.fedex_v0_enabled:
        return {"online": False, "detail": "fedex-v0 désactivé (FEDEX_V0_ENABLED=false)", "latency_ms": None}

    url = f"{_base(s)}/api/health"
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=min(10.0, s.fedex_v0_timeout_seconds)) as client:
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
        logger.warning("fedex-v0 health check failed: %s", exc)
        return {"online": False, "detail": str(exc), "latency_ms": None}


def call_fedex_v0_generate(
    message: str,
    *,
    fedex_v0_session_id: str | None = None,
    settings: Settings | None = None,
) -> tuple[str, str | None, float]:
    """
    Appelle POST /api/voice/generate (stream agrégé côté client httpx).
    Retourne (reply_text, fedex_v0_session_id, latency_ms).
    """
    s = settings or get_settings()
    if not s.fedex_v0_enabled:
        raise fedex-v0BridgeError("fedex-v0 est désactivé sur ce serveur FedEx.")

    url = f"{_base(s)}/api/voice/generate"
    payload = {"message": message, "session_id": fedex_v0_session_id}
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=s.fedex_v0_timeout_seconds) as client:
            resp = client.post(url, json=payload, headers=_headers(s))
            latency = round((time.perf_counter() - started) * 1000, 1)
            if resp.status_code >= 400:
                detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                raise fedex-v0BridgeError(detail, status_code=resp.status_code)
            reply = (resp.text or "").strip()
            if not reply:
                raise fedex-v0BridgeError("Réponse fedex-v0 vide — vérifiez qu'Ollama tourne.")
            new_sid = resp.headers.get("X-Session-Id") or fedex_v0_session_id
            return reply, new_sid, latency
    except fedex-v0BridgeError:
        raise
    except httpx.TimeoutException as exc:
        raise fedex-v0BridgeError(
            f"fedex-v0 n'a pas répondu dans les {int(s.fedex_v0_timeout_seconds)} s — Ollama peut être en cold start."
        ) from exc
    except httpx.RequestError as exc:
        raise fedex-v0BridgeError(
            f"Impossible de joindre fedex-v0 sur {_base(s)} — lancez: python -m fedex_v0.app"
        ) from exc
