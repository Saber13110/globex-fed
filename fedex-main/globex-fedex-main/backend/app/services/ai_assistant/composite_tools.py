"""Outils composites multi-sources (santé plateforme, missions, activité hebdo)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select

from app.models.agent_mission import AgentMission
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext


def _missions_summary(ctx: ToolExecutionContext, args: dict[str, Any]) -> dict[str, Any]:
    limit = min(int(args.get("limit") or 20), 50)
    db = ctx.db
    total = db.scalar(select(func.count()).select_from(AgentMission)) or 0
    rows = db.scalars(
        select(AgentMission).order_by(desc(AgentMission.created_at)).limit(limit)
    ).all()
    items = [
        {
            "id": m.id,
            "title": (m.task_description or "")[:120],
            "task_description": m.task_description,
            "status": m.status,
            "agent_type": m.agent_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]
    return {"status": "ok", "total": total, "showing": len(items), "missions": items}


def _platform_health(ctx: ToolExecutionContext, args: dict[str, Any]) -> dict[str, Any]:
    stats = execute_tool(ctx, ToolCall(name="get_platform_stats", args={}))
    tracking = execute_tool(ctx, ToolCall(name="analyze_tracking", args={"limit": 20}))
    users = execute_tool(ctx, ToolCall(name="analyze_users", args={"limit": 30}))
    tickets = execute_tool(ctx, ToolCall(name="analyze_tickets", args={"status": "open", "limit": 15}))
    notifications = execute_tool(ctx, ToolCall(name="analyze_notifications", args={"limit": 15}))
    security = execute_tool(ctx, ToolCall(name="analyze_security", args={}))
    return {
        "status": "ok",
        "report_type": "platform_health_report",
        "platform_stats": stats.to_function_response(),
        "tracking": tracking.to_function_response(),
        "users": users.to_function_response(),
        "tickets": tickets.to_function_response(),
        "notifications": notifications.to_function_response(),
        "security": security.to_function_response(),
    }


def _security_report(ctx: ToolExecutionContext, args: dict[str, Any]) -> dict[str, Any]:
    """Rapport sécurité complet — incidents, logs suspects, notifications critiques."""
    security = execute_tool(ctx, ToolCall(name="analyze_security", args={"status": "open", "limit": 30}))
    logs = execute_tool(
        ctx,
        ToolCall(name="analyze_suspicious_logs", args={"hours": int(args.get("hours") or 24)}),
    )
    notifications = execute_tool(
        ctx,
        ToolCall(name="analyze_notifications", args={"limit": 20, "critical_only": True}),
    )
    sec_data = security.to_function_response()
    incidents = sec_data.get("incidents") or sec_data.get("sample") or []
    critical = sum(1 for i in incidents if isinstance(i, dict) and str(i.get("severity", "")).lower() in {"critical", "critique", "high", "élevé"})
    return {
        "status": "ok",
        "report_type": "security_report",
        "open_incidents_count": sec_data.get("count") or sec_data.get("total") or len(incidents),
        "critical_count": critical,
        "security": sec_data,
        "suspicious_logs": logs.to_function_response(),
        "critical_notifications": notifications.to_function_response(),
        "risk_level": "élevé" if critical >= 3 else "moyen" if critical else "faible",
        "recommendations": [
            "Surveiller les tentatives de prompt injection",
            "Vérifier les accès admin récents",
            "Traiter les incidents ouverts en priorité",
        ],
    }


def _weekly_activity(ctx: ToolExecutionContext, args: dict[str, Any]) -> dict[str, Any]:
    hours = int(args.get("hours") or 168)
    logs = execute_tool(
        ctx,
        ToolCall(name="analyze_logs", args={"hours": hours, "limit": int(args.get("limit") or 60)}),
    )
    notifs = execute_tool(
        ctx,
        ToolCall(name="analyze_notifications", args={"limit": 20}),
    )
    return {
        "status": "ok",
        "period_hours": hours,
        "logs": logs.to_function_response(),
        "notifications": notifs.to_function_response(),
    }


_COMPOSITE = {
    "get_agent_missions_summary": _missions_summary,
    "analyze_platform_health": _platform_health,
    "analyze_weekly_activity": _weekly_activity,
    "generate_security_report": _security_report,
    "platform_health_report": _platform_health,
}


def run_composite_tool(
    ctx: ToolExecutionContext,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    fn = _COMPOSITE.get(tool_name)
    if fn is None:
        return {"status": "error", "error": f"Outil composite inconnu: {tool_name}"}
    return fn(ctx, args)
