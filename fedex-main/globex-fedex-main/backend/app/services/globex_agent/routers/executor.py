"""Exécution des plans routeur admin → outils métier."""

from __future__ import annotations

from typing import Any

from app.services.globex_agent.tool_catalog import tools_for_admin_task


def plan_to_tool_calls(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Convertit un plan routeur en appels outils (max 3)."""
    task = str(plan.get("task_type") or "")
    answers = dict(plan.get("answers") or {})
    hours = int(answers.get("hours") or 24)
    limit = int(answers.get("limit") or 10)
    fmt = str(answers.get("format") or "pdf").lower()

    mapping: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "analyze_tickets": [("analyze_tickets", {"status": answers.get("status") or "open"})],
        "analyze_users": [("analyze_users", {})],
        "get_platform_stats": [("get_platform_stats", {})],
        "analyze_security": [("analyze_security", {"limit": min(max(limit, 1), 50)})],
        "analyze_logs": [("analyze_logs", {"hours": min(max(hours, 1), 168)})],
        "export_logs": [
            (
                "export_activity_logs_excel" if fmt == "xlsx" else "export_activity_logs_pdf",
                {"hours": min(max(hours, 1), 168)},
            ),
        ],
    }

    calls = mapping.get(task, [])
    allowed = set(tools_for_admin_task(task))
    if allowed:
        calls = [(n, a) for n, a in calls if n in allowed or not allowed]
    return calls[:3]
