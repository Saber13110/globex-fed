"""Routes API Globex Agent — noyau indépendant du copilot."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.globex_agent import (
    GlobexAgentApproveResponse,
    GlobexAgentCatalogItem,
    GlobexAgentCatalogResponse,
    GlobexAgentChatRequest,
    GlobexAgentChatResponse,
    GlobexAgentHealthResponse,
    GlobexAgentStep,
    GlobexAgentToolExecuteRequest,
    GlobexAgentToolExecuteResponse,
    GlobexAgentToolInfo,
    GlobexAgentToolsResponse,
)
from app.services import agent_mission_service as mission_svc
from app.services.activity_log_service import client_ip
from app.services.globex_agent.kernel import (
    check_globex_agent_health,
    execute_globex_tool,
    list_globex_agent_tools,
    run_globex_agent_chat,
)
from app.services.prompt_guard_service import assess_user_message, must_block_preferences

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/globex-agent", tags=["globex-agent"])


def _approval_reply_from_mission(mission: object | None, *, approved: bool) -> str:
    if not approved:
        return "Action refusée — rien n'a été exécuté."
    if mission is None:
        return "Action approuvée."
    steps = getattr(mission, "steps", None) or []
    for step in reversed(steps):
        raw = getattr(step, "output_json", None) or ""
        if not raw:
            continue
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(out, dict):
            answer = out.get("task_answer") or out.get("reply")
            if answer:
                return str(answer).strip()
    mid = getattr(mission, "id", None)
    return f"Action approuvée — mission #{mid}." if mid else "Action approuvée."


def _ensure_enabled() -> None:
    if not get_settings().globex_agent_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Globex Agent désactivé (GLOBEX_AGENT_ENABLED=false).",
        )


@router.get("/health", response_model=GlobexAgentHealthResponse)
def globex_agent_health(
    _: User = Depends(require_role("admin")),
) -> GlobexAgentHealthResponse:
    _ensure_enabled()
    data = check_globex_agent_health()
    from app.services.globex_agent.proactive_scheduler import get_proactive_status

    data["proactive"] = get_proactive_status()
    return GlobexAgentHealthResponse(**data)


@router.get("/tools", response_model=GlobexAgentToolsResponse)
def globex_agent_tools(
    agent_mode: bool = True,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> GlobexAgentToolsResponse:
    _ensure_enabled()
    items = list_globex_agent_tools(db, admin, agent_mode=agent_mode)
    return GlobexAgentToolsResponse(
        tools=[GlobexAgentToolInfo(**t) for t in items],
    )


@router.get("/tools/catalog", response_model=GlobexAgentCatalogResponse)
def globex_agent_tools_catalog(
    _: User = Depends(require_role("admin")),
) -> GlobexAgentCatalogResponse:
    """Catalogue complet des 62 outils admin avec métadonnées phase/groupe."""
    _ensure_enabled()
    from app.services.globex_agent.tool_catalog import build_tool_catalog, catalog_summary

    summary = catalog_summary()
    catalog = build_tool_catalog()
    return GlobexAgentCatalogResponse(
        registered_count=summary["registered_count"],
        complete=summary["complete"],
        tools=[GlobexAgentCatalogItem(**item) for item in catalog],
        groups=summary["groups"],
        phases=summary["phases"],
        missing_handlers=summary["missing_handlers"],
    )


@router.post("/chat", response_model=GlobexAgentChatResponse)
def globex_agent_chat(
    payload: GlobexAgentChatRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> GlobexAgentChatResponse:
    """Chat Globex OS — Ollama + outils métier (sans copilot)."""
    _ensure_enabled()
    settings = get_settings()
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message requis.")

    if settings.prompt_guard_enabled:
        risk = assess_user_message(message)
        if must_block_preferences(risk) and settings.prompt_guard_block_chat:
            raise HTTPException(status_code=403, detail="Message bloqué par la politique de sécurité.")

    logger.info("[GlobexAgent] chat — %.120s agent_mode=%s", message, payload.agent_mode)
    try:
        hist = [{"role": m.role, "content": m.content} for m in payload.conversation_history]
        result = run_globex_agent_chat(
            db,
            admin,
            message,
            agent_mode=payload.agent_mode,
            conversation_history=hist,
            ui_language=payload.ui_language,
            ip_address=client_ip(request),
        )
    except Exception as exc:
        logger.exception("[GlobexAgent] erreur chat")
        raise HTTPException(status_code=503, detail=str(exc)[:300]) from exc

    steps = [
        GlobexAgentStep(label=s.get("label", ""), status=s.get("status", ""), detail=s.get("detail"))
        for s in (result.get("agent_steps") or [])
        if isinstance(s, dict)
    ]
    return GlobexAgentChatResponse(
        reply=result.get("reply") or "",
        mode=result.get("mode") or "jarvis",
        tools_used=result.get("tools_used") or [],
        agent_steps=steps,
        needs_approval=bool(result.get("needs_approval")),
        approval_id=result.get("approval_id"),
        approval_hint=result.get("approval_hint"),
        mission_id=result.get("mission_id"),
        action_executed=bool(result.get("action_executed")),
        export_download=result.get("export_download"),
        llm_degraded=bool(result.get("llm_degraded")),
        intent=result.get("intent"),
        execution_time_ms=result.get("execution_time_ms"),
    )


@router.post("/tools/execute", response_model=GlobexAgentToolExecuteResponse)
def globex_agent_tool_execute(
    payload: GlobexAgentToolExecuteRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> GlobexAgentToolExecuteResponse:
    _ensure_enabled()
    result = execute_globex_tool(
        db,
        admin,
        payload.tool,
        payload.args,
        agent_mode=payload.agent_mode,
    )
    return GlobexAgentToolExecuteResponse(**result)


@router.get("/workspace/overview")
def globex_workspace_overview(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    from app.services.globex_agent.workspace_bridge import build_workspace_overview

    return build_workspace_overview(db, admin)


@router.get("/workspace/initiatives")
def globex_workspace_initiatives(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = 30,
) -> list[dict]:
    _ensure_enabled()
    from app.services.globex_agent.workspace_bridge import list_workspace_initiatives

    return list_workspace_initiatives(db, limit=min(max(limit, 1), 50))


@router.get("/workspace/missions")
def globex_workspace_missions(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = 40,
) -> list[dict]:
    _ensure_enabled()
    from app.services.globex_agent.workspace_bridge import list_workspace_missions

    return list_workspace_missions(db, limit=min(max(limit, 1), 80))


@router.get("/workspace/analytics")
def globex_workspace_analytics(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_enabled()
    from app.services.globex_agent.workspace_bridge import build_workspace_analytics

    return build_workspace_analytics(db, admin)


@router.post("/proactive/run")
def globex_proactive_run(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    """Déclenche manuellement un cycle proactif (SLA + dormants) — debug / test."""
    _ensure_enabled()
    from app.services.globex_agent.proactive_scheduler import run_proactive_scan_cycle

    summary = run_proactive_scan_cycle(db)
    return {"status": "ok", "summary": summary}


@router.get("/proactive/status")
def globex_proactive_status(
    _: User = Depends(require_role("admin")),
) -> dict:
    _ensure_enabled()
    from app.services.globex_agent.proactive_scheduler import get_proactive_status

    return get_proactive_status()


@router.post("/approve/{approval_id}", response_model=GlobexAgentApproveResponse)
def globex_agent_approve(
    approval_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> GlobexAgentApproveResponse:
    """Approuve une action sensible initiée par Globex Agent."""
    _ensure_enabled()
    approval, mission = mission_svc.approve_request(db, approval_id, admin)
    reply = _approval_reply_from_mission(mission, approved=True)
    return GlobexAgentApproveResponse(
        approval_id=approval.id,
        status=approval.status,
        reply=reply,
        mission_id=mission.id if mission else None,
    )


@router.post("/reject/{approval_id}", response_model=GlobexAgentApproveResponse)
def globex_agent_reject(
    approval_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> GlobexAgentApproveResponse:
    _ensure_enabled()
    approval, mission = mission_svc.reject_request(db, approval_id, admin)
    return GlobexAgentApproveResponse(
        approval_id=approval.id,
        status=approval.status,
        reply=_approval_reply_from_mission(mission, approved=False),
        mission_id=mission.id if mission else None,
    )
