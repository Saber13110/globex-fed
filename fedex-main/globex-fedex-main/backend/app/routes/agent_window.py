"""Routes admin — Agent Window (intégration Jarvis-OS)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.agent_window import (
    AgentWindowChatRequest,
    AgentWindowChatResponse,
    AgentWindowHealthResponse,
    AgentWindowSessionDetail,
    AgentWindowSessionListResponse,
)
from app.services.activity_log_service import client_ip
from app.services.jarvis.agent_window_service import process_agent_window_chat
from app.services.jarvis.bridge import check_jarvis_health
from app.services.jarvis.session_service import archive_session, get_session_detail, list_sessions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/agent-window", tags=["admin-agent-window"])


@router.get("/health", response_model=AgentWindowHealthResponse)
def agent_window_health(
    _: User = Depends(require_role("admin")),
) -> AgentWindowHealthResponse:
    settings = get_settings()
    if not settings.jarvis_enabled:
        return AgentWindowHealthResponse(
            enabled=False,
            online=False,
            jarvis_base_url=settings.jarvis_base_url,
            detail="JARVIS_ENABLED=false",
        )
    health = check_jarvis_health(settings)
    return AgentWindowHealthResponse(
        enabled=True,
        online=bool(health.get("online")),
        jarvis_base_url=settings.jarvis_base_url,
        detail=health.get("detail"),
        latency_ms=health.get("latency_ms"),
    )


@router.get("/sessions", response_model=AgentWindowSessionListResponse)
def list_agent_window_sessions(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentWindowSessionListResponse:
    return AgentWindowSessionListResponse(sessions=list_sessions(db, admin.id))


@router.get("/sessions/{session_id}", response_model=AgentWindowSessionDetail)
def get_agent_window_session(
    session_id: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentWindowSessionDetail:
    detail = get_session_detail(db, session_id, admin.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable.")
    return detail


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_window_session(
    session_id: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    if not archive_session(db, session_id, admin.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable.")
    db.commit()


@router.post("/chat", response_model=AgentWindowChatResponse)
def agent_window_chat(
    payload: AgentWindowChatRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentWindowChatResponse:
    settings = get_settings()
    if not settings.jarvis_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jarvis est désactivé. Définissez JARVIS_ENABLED=true dans .env.",
        )
    logger.info("[AgentWindow] message — %.120s", payload.message)
    return process_agent_window_chat(
        db,
        admin,
        payload,
        ip_address=client_ip(request),
    )
