"""Orchestration Agent Window — BFF FedEx → Jarvis sidecar."""

from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.schemas.agent_window import AgentWindowChatRequest, AgentWindowChatResponse
from app.services.activity_log_service import write_log
from app.services.jarvis.bridge import JarvisBridgeError, call_jarvis_generate
from app.services.jarvis.context_builder import build_globex_context_block
from app.services.jarvis.prompt_composer import compose_jarvis_user_message
from app.services.jarvis.session_service import append_message, create_session, get_session
from app.services.prompt_guard_service import assess_user_message, must_block_preferences

_SENSITIVE_PATTERNS = re.compile(
    r"\b("
    r"suspend|suspendre|supprim|delete|réactiv|reactiv|"
    r"envoi[e]?r?\s+(un\s+)?mail|send\s+email|approbation|"
    r"mission\s+agent|bloquer\s+le\s+compte"
    r")\b",
    re.I,
)


def _detect_sensitive_action(message: str) -> bool:
    return bool(_SENSITIVE_PATTERNS.search(message or ""))


def _sensitive_redirect_reply() -> str:
    return (
        "Cette demande implique une **action sensible** sur la plateforme Globex "
        "(compte, export, e-mail, mission agent…).\n\n"
        "Utilisez l'onglet **Jarvis** en **mode Agent** — "
        "les actions passent par les outils métier et les approbations admin.\n\n"
        "Jarvis Agent Window reste réservé à l'analyse, la synthèse et l'aide à la décision."
    )


def process_agent_window_chat(
    db: Session,
    admin: User,
    payload: AgentWindowChatRequest,
    *,
    ip_address: str = "",
) -> AgentWindowChatResponse:
    settings = get_settings()
    message = (payload.message or "").strip()
    has_attachment = bool((payload.image_base64 or "").strip())
    if not message and not has_attachment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message requis.")

    if message and settings.prompt_guard_enabled:
        risk = assess_user_message(message)
        if must_block_preferences(risk) and settings.prompt_guard_block_chat:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Message bloqué par la politique de sécurité Globex.",
            )

    session = None
    if payload.session_id:
        session = get_session(db, payload.session_id, admin.id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable.")
    else:
        session = create_session(db, admin)

    append_message(db, session, sender="admin", message_text=message)

    if _detect_sensitive_action(message):
        reply = _sensitive_redirect_reply()
        append_message(db, session, sender="system", message_text=reply)
        db.commit()
        write_log(
            db,
            action="admin.jarvis_window.redirect_copilot",
            message=message[:120],
            category="admin",
            level="INFO",
            actor_user_id=admin.id,
            ip_address=ip_address,
            metadata={"session_id": session.id},
        )
        return AgentWindowChatResponse(
            reply=reply,
            session_id=session.id,
            jarvis_session_id=session.jarvis_session_id,
            engine="globex-guard",
            redirect_to_copilot=True,
            copilot_hint=message,
        )

    if settings.globex_simple_mode:
        from app.services.globex_agent.kernel import run_globex_agent_chat

        hist = [
            {"role": item.role, "content": item.content}
            for item in (payload.conversation_history or [])
        ]
        try:
            result = run_globex_agent_chat(
                db,
                admin,
                message,
                agent_mode=True,
                conversation_history=hist,
                ui_language=payload.ui_language or "fr",
                ip_address=ip_address,
                chat_session_id=payload.chat_session_id,
                image_base64=payload.image_base64,
                image_mime_type=payload.image_mime_type,
                file_name=payload.file_name,
            )
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc)[:300],
            ) from exc

        reply = result.get("reply") or ""
        latency = result.get("execution_time_ms")
        append_message(db, session, sender="jarvis", message_text=reply, latency_ms=latency)
        db.commit()

        write_log(
            db,
            action="admin.jarvis_window.chat",
            message=message[:120],
            category="admin",
            level="INFO",
            actor_user_id=admin.id,
            ip_address=ip_address,
            metadata={
                "session_id": session.id,
                "engine": "globex-agent",
                "latency_ms": latency,
                "simple_mode": True,
            },
        )

        return AgentWindowChatResponse(
            reply=reply,
            session_id=session.id,
            jarvis_session_id=session.jarvis_session_id,
            engine="globex-agent",
            latency_ms=latency,
            shipment=result.get("shipment"),
            chat_session_id=result.get("chat_session_id"),
            export_download=result.get("export_download"),
        )

    context = build_globex_context_block(db, admin)
    jarvis_payload = compose_jarvis_user_message(
        message,
        context_block=context,
        conversation_history=payload.conversation_history,
        max_history_turns=settings.jarvis_max_history_turns,
    )

    try:
        reply, jarvis_sid, latency = call_jarvis_generate(
            jarvis_payload,
            jarvis_session_id=session.jarvis_session_id,
        )
    except JarvisBridgeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if jarvis_sid:
        session.jarvis_session_id = jarvis_sid

    append_message(db, session, sender="jarvis", message_text=reply, latency_ms=latency)
    db.commit()

    write_log(
        db,
        action="admin.jarvis_window.chat",
        message=message[:120],
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=ip_address,
        metadata={
            "session_id": session.id,
            "jarvis_session_id": session.jarvis_session_id,
            "latency_ms": latency,
        },
    )

    return AgentWindowChatResponse(
        reply=reply,
        session_id=session.id,
        jarvis_session_id=session.jarvis_session_id,
        engine="jarvis-local",
        latency_ms=latency,
    )
