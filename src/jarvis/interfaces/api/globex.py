"""Proxy Jarvis UI → API Globex Agent (FedEx backend)."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel, Field

from jarvis.kernel.settings import settings

router = APIRouter()

_token_cache: dict[str, Any] = {"token": "", "expires_at": 0.0}
_CAPTURE_DIR = Path(settings.memory_dir) / "captures"


class GlobexChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    agent_mode: bool = True
    ui_language: str = "fr"
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    chat_session_id: int | None = None
    image_base64: str | None = None
    image_mime_type: str | None = None
    file_name: str | None = None


class GlobexChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)
    needs_approval: bool = False
    approval_id: int | None = None
    approval_hint: str | None = None
    mission_id: int | None = None
    action_executed: bool = False
    export_download: dict[str, Any] | None = None
    client_action: dict[str, Any] | None = None
    capture_download: dict[str, Any] | None = None
    mode: str = "jarvis"
    llm_degraded: bool = False
    execution_time_ms: float | None = None
    chat_session_id: int | None = None
    intent: str | None = None
    shipment: dict[str, Any] | None = None


class GlobexApprovalResponse(BaseModel):
    approval_id: int
    status: str
    reply: str | None = None
    mission_id: int | None = None


async def _fedex_login() -> str:
    email = (settings.globex_admin_email or "").strip()
    password = settings.globex_admin_password.get_secret_value()
    if not email or not password:
        raise HTTPException(
            status_code=503,
            detail="Globex OS : configurez GLOBEX_ADMIN_EMAIL et GLOBEX_ADMIN_PASSWORD dans .env Jarvis.",
        )
    base = settings.globex_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base}/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code >= 400:
            detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            raise HTTPException(status_code=503, detail=f"Login Globex échoué : {detail}")
        data = resp.json()
        if data.get("requires_2fa"):
            raise HTTPException(
                status_code=503,
                detail="Globex OS : le compte admin exige la 2FA — désactivez TWO_FACTOR_ENABLED pour l'admin ou utilisez un token JWT manuel.",
            )
        token = data.get("access_token") or ""
        if not token:
            raise HTTPException(status_code=503, detail="Login Globex : pas de access_token.")
        return token


async def _get_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < float(_token_cache["expires_at"]):
        return str(_token_cache["token"])
    token = await _fedex_login()
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + 3600
    return token


def _chat_response_from_data(data: dict[str, Any]) -> GlobexChatResponse:
    export_dl = data.get("export_download")
    cap_dl = data.get("capture_download")
    client_action = data.get("client_action")
    shipment = data.get("shipment")
    return GlobexChatResponse(
        reply=data.get("reply") or "Pas de réponse du serveur Globex.",
        tools_used=data.get("tools_used") or [],
        needs_approval=bool(data.get("needs_approval")),
        approval_id=data.get("approval_id"),
        approval_hint=data.get("approval_hint"),
        mission_id=data.get("mission_id"),
        action_executed=bool(data.get("action_executed")),
        export_download=export_dl if isinstance(export_dl, dict) else None,
        client_action=client_action if isinstance(client_action, dict) else None,
        capture_download=cap_dl if isinstance(cap_dl, dict) else None,
        mode=data.get("mode") or "jarvis",
        llm_degraded=bool(data.get("llm_degraded")),
        execution_time_ms=data.get("execution_time_ms"),
        chat_session_id=data.get("chat_session_id"),
        intent=data.get("intent"),
        shipment=shipment if isinstance(shipment, dict) else None,
    )


def _looks_like_capture_request(message: str) -> bool:
    text = (message or "").lower()
    return bool(
        re.search(
            r"\b(capture|capturer|screenshot|imprime?.?écran|photo\s+(de\s+)?l?.?écran|"
            r"zone\s+notification|partie\s+.{0,20}admin)\b",
            text,
        )
    )


def _looks_like_export_request(message: str, history: list[dict[str, str]]) -> bool:
    text = (message or "").lower()
    if re.search(r"\b(pdf|export|exporter|t[eé]l[eé]charger|mettre en|fichier)\b", text):
        return True
    if history and re.search(r"\b(mets?|met|mettre|envoie|g[eé]n[eè]re)\b", text):
        return True
    return False


async def invoke_globex_chat(
    message: str,
    *,
    agent_mode: bool = True,
    ui_language: str = "fr",
    conversation_history: list[dict[str, str]] | None = None,
    chat_session_id: int | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    file_name: str | None = None,
) -> GlobexChatResponse:
    """Appelle l'API Globex Agent FedEx (utilisé par proxy HTTP, voix, etc.)."""
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé (GLOBEX_OS_ENABLED=false).")

    token = await _get_token()
    base = settings.globex_api_url.rstrip("/")
    history = conversation_history or []
    payload: dict[str, Any] = {
        "message": message,
        "agent_mode": agent_mode,
        "ui_language": ui_language,
        "conversation_history": history,
    }
    if chat_session_id is not None:
        payload["chat_session_id"] = chat_session_id
    if image_base64:
        payload["image_base64"] = image_base64
    if image_mime_type:
        payload["image_mime_type"] = image_mime_type
    if file_name:
        payload["file_name"] = file_name

    timeout = 360.0 if _looks_like_export_request(message, history) else 300.0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/api/globex-agent/chat",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Globex Agent timeout ({int(timeout)}s) — Ollama peut être en cold start.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de joindre Globex FedEx ({base}) : {exc}",
        ) from exc

    if resp.status_code == 401:
        _token_cache["token"] = ""
        _token_cache["expires_at"] = 0.0
        raise HTTPException(status_code=503, detail="Session Globex expirée — réessayez.")

    if resp.status_code >= 400:
        detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return _chat_response_from_data(resp.json())


def _export_download_path(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Mappe export_download → route FedEx + query params."""
    preset = str(spec.get("preset") or "").strip()
    fmt = str(spec.get("format") or "pdf").lower()
    params: dict[str, Any] = {}

    if preset == "admin_logs":
        hours = int(spec.get("hours") or 24)
        params["hours"] = hours
        if fmt == "xlsx":
            return "/admin/ai-assistant/export/activity-logs.xlsx", params
        if fmt == "csv":
            return "/admin/ai-assistant/export/activity-logs.csv", params
        return "/admin/ai-assistant/export/activity-logs.pdf", params

    if preset == "admin_tracking" and spec.get("tracking_numbers"):
        params["numbers"] = str(spec["tracking_numbers"])
        return "/admin/ai-assistant/export/tracking-status.pdf", params

    params["preset"] = preset or "admin_generic"
    if spec.get("limit") is not None:
        params["limit"] = int(spec["limit"])
    elif spec.get("records") is not None:
        params["limit"] = int(spec["records"])
    if spec.get("module"):
        params["module"] = str(spec["module"])
    if spec.get("export_token"):
        params["export_token"] = str(spec["export_token"])
    if spec.get("hours") is not None:
        params["hours"] = int(spec["hours"])

    if fmt == "xlsx":
        return "/admin/ai-assistant/export/context.xlsx", params
    return "/admin/ai-assistant/export/context.pdf", params


@router.get("/api/globex/health")
async def globex_proxy_health() -> dict[str, Any]:
    if not settings.globex_os_enabled:
        return {"enabled": False, "detail": "GLOBEX_OS_ENABLED=false"}
    base = settings.globex_api_url.rstrip("/")
    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base}/api/globex-agent/health",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json() if resp.content else {}
            return {
                "enabled": True,
                "fedex_status": resp.status_code,
                "fedex": data,
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Globex health check failed: {}", exc)
        return {"enabled": True, "fedex_status": 0, "detail": str(exc)}


@router.get("/api/globex/security/latest-incident")
async def globex_latest_security_incident() -> dict[str, Any]:
    """Dernier incident IDS ouvert (geste paume ouverte Fedex-v0)."""
    return await fetch_latest_security_incident()


async def fetch_latest_security_incident() -> dict[str, Any]:
    """Dernier incident IDS — HTTP ou WebSocket vision."""
    if not settings.globex_os_enabled:
        return {"found": False, "incident": None, "error": "Globex OS désactivé."}
    try:
        token = await _get_token()
    except HTTPException as exc:
        return {"found": False, "incident": None, "error": str(exc.detail)}
    except Exception as exc:
        return {"found": False, "incident": None, "error": str(exc)}

    base = settings.globex_api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}

    async def _fetch(status: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{base}/admin/security/incidents",
                headers=headers,
                params={"status": status, "limit": 1, "offset": 0},
            )
        if resp.status_code >= 400:
            detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            raise HTTPException(status_code=resp.status_code, detail=detail)
        data = resp.json() if resp.content else {}
        items = data.get("items") if isinstance(data, dict) else []
        return items if isinstance(items, list) else []

    try:
        items = await _fetch("open")
        if not items:
            items = await _fetch("all")
    except HTTPException as exc:
        return {"found": False, "incident": None, "error": str(exc.detail)}
    except Exception as exc:
        return {"found": False, "incident": None, "error": str(exc)}

    if not items:
        return {"found": False, "incident": None}
    inc = items[0]
    return {"found": True, "incident": inc, "admin_url": f"/admin?section=incidents&incident={inc.get('id')}"}


@router.post("/api/globex/chat", response_model=GlobexChatResponse)
async def globex_proxy_chat(body: GlobexChatRequest) -> GlobexChatResponse:
    message = (body.message or "").strip()
    has_attachment = bool((body.image_base64 or "").strip())
    if not message and not has_attachment:
        raise HTTPException(status_code=400, detail="Message requis.")
    result = await invoke_globex_chat(
        message,
        agent_mode=body.agent_mode,
        ui_language=body.ui_language,
        conversation_history=body.conversation_history,
        chat_session_id=body.chat_session_id,
        image_base64=body.image_base64,
        image_mime_type=body.image_mime_type,
        file_name=body.file_name,
    )
    if _looks_like_capture_request(message):
        reply = result.reply or ""
        if "sélectionnez" not in reply.lower() and "capture" not in reply.lower():
            reply = (reply.rstrip() + "\n\n📷 Sélectionnez la zone à capturer à l'écran.").strip()
        result = result.model_copy(
            update={
                "reply": reply,
                "client_action": {
                    "type": "capture_region",
                    "hint": message[:300],
                },
            }
        )
    return result


@router.post("/api/globex/capture")
async def globex_upload_capture(
    file: UploadFile = File(...),
    hint: str = Form(""),
) -> dict[str, Any]:
    """Enregistre une capture PNG côté Jarvis (téléchargement via proxy)."""
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")

    content_type = (file.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Seules les images sont acceptées.")

    raw = await file.read()
    if not raw or len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier vide ou trop volumineux (max 12 Mo).")

    _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    capture_id = uuid.uuid4().hex[:16]
    ext = ".png"
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()[:8]
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        ext = ".png"
    filename = f"capture-{capture_id}{ext}"
    path = _CAPTURE_DIR / filename
    path.write_bytes(raw)

    spec = {
        "capture_id": capture_id,
        "filename": filename,
        "hint": (hint or "")[:300],
    }
    logger.info("Globex capture saved {} ({} bytes)", filename, len(raw))
    return {"ok": True, "capture_download": spec}


@router.get("/api/globex/capture/download")
async def globex_download_capture(
    capture_id: str = Query(..., min_length=8, max_length=32),
    filename: str = Query("capture.png", max_length=200),
) -> Response:
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")

    safe_name = Path(filename).name
    if not safe_name.startswith("capture-") or capture_id not in safe_name:
        safe_name = f"capture-{capture_id}.png"

    path = _CAPTURE_DIR / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Capture introuvable ou expirée.")

    data = path.read_bytes()
    media = "image/png"
    if safe_name.endswith(".jpg") or safe_name.endswith(".jpeg"):
        media = "image/jpeg"
    elif safe_name.endswith(".webp"):
        media = "image/webp"

    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.post("/api/globex/approve/{approval_id}", response_model=GlobexApprovalResponse)
async def globex_proxy_approve(approval_id: int) -> GlobexApprovalResponse:
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")
    token = await _get_token()
    base = settings.globex_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base}/api/globex-agent/approve/{approval_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)
    data = resp.json()
    return GlobexApprovalResponse(
        approval_id=int(data.get("approval_id") or approval_id),
        status=str(data.get("status") or "approved"),
        reply=data.get("reply"),
        mission_id=data.get("mission_id"),
    )


@router.post("/api/globex/reject/{approval_id}", response_model=GlobexApprovalResponse)
async def globex_proxy_reject(approval_id: int) -> GlobexApprovalResponse:
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")
    token = await _get_token()
    base = settings.globex_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base}/api/globex-agent/reject/{approval_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)
    data = resp.json()
    return GlobexApprovalResponse(
        approval_id=int(data.get("approval_id") or approval_id),
        status=str(data.get("status") or "rejected"),
        reply=data.get("reply"),
        mission_id=data.get("mission_id"),
    )


@router.get("/api/globex/export/download")
async def globex_proxy_export_download(
    preset: str = Query(..., min_length=2, max_length=64),
    filename: str = Query("export.pdf", max_length=200),
    fmt: str = Query("pdf", alias="format", max_length=8),
    limit: int | None = Query(None, ge=1, le=100),
    module: str | None = Query(None, max_length=32),
    export_token: str | None = Query(None, min_length=8, max_length=64),
    hours: int | None = Query(None, ge=1, le=168),
    tracking_numbers: str | None = Query(None, max_length=500),
) -> Response:
    """Télécharge un export FedEx via le token admin Jarvis (proxy sécurisé)."""
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")

    spec: dict[str, Any] = {
        "preset": preset,
        "filename": filename,
        "format": fmt,
    }
    if limit is not None:
        spec["limit"] = limit
    if module:
        spec["module"] = module
    if export_token:
        spec["export_token"] = export_token
    if hours is not None:
        spec["hours"] = hours
    if tracking_numbers:
        spec["tracking_numbers"] = tracking_numbers

    path, params = _export_download_path(spec)
    token = await _get_token()
    base = settings.globex_api_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(
                f"{base}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Export FedEx indisponible : {exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    content_type = resp.headers.get("content-type") or "application/octet-stream"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=resp.content, media_type=content_type, headers=headers)
