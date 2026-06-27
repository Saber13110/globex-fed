"""Pont Workspace — agrège approbations, missions et KPI pour le dashboard Jarvis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.agent_approval_request import AgentApprovalRequest
from app.models.agent_mission import AgentMission
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserStatus
from app.services.gpt.tool_handlers import _handle_analyze_tracking, _handle_get_platform_stats
from app.services.globex_agent.dormant_accounts_service import dormant_summary_lines, scan_dormant_accounts
from app.services.globex_agent.ticket_sla_service import scan_sla_breaches, sla_summary_lines
from app.services.gpt.tool_types import ToolExecutionContext


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _priority_for_action(action_type: str) -> str:
    if action_type in {
        "suspend_user",
        "suspend_users_bulk",
        "notify_all_users",
        "send_bulk_email",
        "run_security_scan",
        "escalate_ticket",
    }:
        return "high"
    if action_type in {"send_client_email", "send_email", "reply_support_ticket", "close_ticket"}:
        return "med"
    return "low"


def _sla_initiatives(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    """Alertes SLA — lecture seule, pas d'approbation."""
    out: list[dict[str, Any]] = []
    for b in scan_sla_breaches(db, limit=limit):
        out.append(
            {
                "id": f"globex-sla-{b['ticket_id']}",
                "source": "globex",
                "type": "sla_alert",
                "title": f"SLA dépassé — ticket #{b['ticket_id']}",
                "context": b.get("subject") or "",
                "reasoning": (
                    f"Retard {b['overdue_hours']}h (SLA {b['sla_hours']}h, "
                    f"priorité {b['priority']})"
                ),
                "action": "scan_ticket_sla",
                "priority": "high" if b.get("priority") in {"high", "urgent", "critical"} else "med",
                "execution_mode": "info",
                "requires_validation": False,
                "ticket_id": b["ticket_id"],
                "created_at": _now_iso(),
            }
        )
    return out


def _dormant_initiatives(db: Session, *, limit: int = 5) -> list[dict[str, Any]]:
    """Comptes inactifs — signal informatif pour l'admin."""
    out: list[dict[str, Any]] = []
    for row in scan_dormant_accounts(db, days=30, limit=limit):
        name = (row.get("full_name") or row.get("email") or "").strip()
        out.append(
            {
                "id": f"globex-dormant-{row['user_id']}",
                "source": "globex",
                "type": "dormant_account",
                "title": f"Compte inactif — {name}",
                "context": row.get("email") or "",
                "reasoning": (
                    f"Aucune activité depuis {row['days_inactive']} jours "
                    f"(seuil {row.get('dormant_days_threshold', 30)}j)."
                ),
                "action": "scan_dormant_accounts",
                "priority": "med",
                "execution_mode": "info",
                "requires_validation": False,
                "user_id": row["user_id"],
                "created_at": _now_iso(),
            },
        )
    return out


def list_workspace_initiatives(db: Session, *, limit: int = 30) -> list[dict[str, Any]]:
    """Approbations pending + alertes SLA + comptes dormants."""
    sla = _sla_initiatives(db, limit=5)
    dormant = _dormant_initiatives(db, limit=5)
    rows = list(
        db.scalars(
            select(AgentApprovalRequest)
            .where(AgentApprovalRequest.status == "pending")
            .order_by(desc(AgentApprovalRequest.created_at))
            .limit(limit)
        ).all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        tool = str(payload.get("tool") or row.action_type or "action")
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        pr = _priority_for_action(tool)
        out.append(
            {
                "id": f"globex-approval-{row.id}",
                "source": "globex",
                "type": tool,
                "title": row.description[:200] if row.description else f"Action : {tool}",
                "context": f"Mission #{row.mission_id} — outil {tool}",
                "reasoning": row.description or "",
                "action": tool,
                "priority": pr,
                "execution_mode": "validate",
                "draft_content": json.dumps(args, ensure_ascii=False, indent=2) if args else "",
                "created_at": row.created_at.isoformat() if row.created_at else _now_iso(),
                "autonomy_level": 5,
                "permission_required": "globex_action",
                "requires_validation": True,
                "approval_id": row.id,
                "mission_id": row.mission_id,
                "tool": tool,
                "args": args,
            }
        )
    return dormant + sla + out


def list_workspace_missions(db: Session, *, limit: int = 40) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(AgentMission)
            .options(joinedload(AgentMission.steps))
            .order_by(desc(AgentMission.updated_at))
            .limit(limit)
        ).all()
    )
    out: list[dict[str, Any]] = []
    for m in rows:
        steps = m.steps or []
        done = sum(1 for s in steps if s.status in {"completed", "done"})
        total = len(steps) or 1
        out.append(
            {
                "id": m.id,
                "source": "globex",
                "agent_type": m.agent_type,
                "title": (m.task_description or "")[:120],
                "status": m.status,
                "schedule_type": m.schedule_type,
                "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                "steps_done": done,
                "steps_total": total,
                "progress": done / total,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return out


def build_workspace_overview(db: Session, admin: User) -> dict[str, Any]:
    """KPI + signaux pour l'onglet Aperçu."""
    ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug="fedex-admin-ops",
        actor_admin_id=admin.id,
    )
    stats = _handle_get_platform_stats(ctx, {}).data if _handle_get_platform_stats(ctx, {}).success else {}
    tracking = _handle_analyze_tracking(ctx, {"limit": 50}).data if True else {}
    delayed = int(tracking.get("delayed_count") or 0)
    pending_approvals = int(
        db.scalar(
            select(func.count())
            .select_from(AgentApprovalRequest)
            .where(AgentApprovalRequest.status == "pending")
        )
        or 0
    )
    open_tickets = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status == SupportTicketStatus.open)
        )
        or 0
    )
    suspended_users = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.suspended.value)
        )
        or 0
    )
    track_total = int(
        db.scalar(select(func.count()).select_from(TrackingRequest)) or 0
    )
    sla_breaches = scan_sla_breaches(db, limit=10)
    sla_count = len(sla_breaches)
    dormant_rows = scan_dormant_accounts(db, days=30, limit=10)
    dormant_count = len(dormant_rows)
    briefing = [
        f"{track_total} colis suivis en base",
        f"{delayed} colis en retard / exception",
        f"{open_tickets} tickets ouverts",
        f"{pending_approvals} action(s) en attente de validation",
        f"{suspended_users} comptes suspendus",
    ]
    briefing.extend(sla_summary_lines(db))
    briefing.extend(dormant_summary_lines(db))
    return {
        "generated_at": _now_iso(),
        "platform_stats": stats,
        "signals": {
            "tracking_total": track_total,
            "tracking_delayed": delayed,
            "open_tickets": open_tickets,
            "pending_approvals": pending_approvals,
            "suspended_users": suspended_users,
            "sla_breaches": sla_count,
            "dormant_accounts": dormant_count,
        },
        "sla_breaches": sla_breaches,
        "dormant_accounts": dormant_rows,
        "briefing_lines": briefing,
    }


def build_workspace_analytics(db: Session, admin: User) -> dict[str, Any]:
    """Métriques plateforme + catalogue + proactif pour l'onglet Analytics Workspace."""
    overview = build_workspace_overview(db, admin)
    signals = overview.get("signals") or {}

    from app.services.globex_agent.proactive_scheduler import get_proactive_status
    from app.services.globex_agent.tool_catalog import build_tool_catalog, catalog_summary

    catalog = catalog_summary()
    missions_total = int(
        db.scalar(select(func.count()).select_from(AgentMission)) or 0
    )
    missions_active = int(
        db.scalar(
            select(func.count())
            .select_from(AgentMission)
            .where(AgentMission.status.notin_(["completed", "failed", "done", "cancelled"]))
        )
        or 0
    )
    approvals_total = int(
        db.scalar(select(func.count()).select_from(AgentApprovalRequest)) or 0
    )
    approvals_pending = int(signals.get("pending_approvals") or 0)

    groups = catalog.get("groups") or {}
    return {
        "generated_at": _now_iso(),
        "kernel_version": "llm-first-v5-phase6",
        "signals": signals,
        "platform_stats": overview.get("platform_stats") or {},
        "missions": {
            "total": missions_total,
            "active": missions_active,
        },
        "approvals": {
            "total": approvals_total,
            "pending": approvals_pending,
        },
        "catalog": {
            "target_count": catalog.get("target_count", 62),
            "registered_count": catalog.get("registered_count", 0),
            "complete": catalog.get("complete", False),
            "groups": groups,
            "phases": catalog.get("phases") or {},
        },
        "proactive": get_proactive_status(),
        "tool_samples": [
            {"name": t["name"], "group": t["group"], "approval_mode": t["approval_mode"]}
            for t in build_tool_catalog()[:12]
        ],
    }
