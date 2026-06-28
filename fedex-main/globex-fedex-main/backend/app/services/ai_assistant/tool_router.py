"""Routage outils selon l'intention classifiée."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.ai_assistant.intent_classifier_v2 import ClassifiedIntent, CopilotIntent
from app.services.ai_assistant.tool_planner import (
    _ANALYTICS_USERS_PLAN,
    _PLATFORM_HEALTH_PLAN,
    _SECURITY_REPORT_PLAN,
)

ToolPlan = list[tuple[str, dict[str, Any]]]


@dataclass
class ToolRoute:
    plan: ToolPlan = field(default_factory=list)
    memory_only: bool = False
    export_module: str | None = None
    export_single: bool = False


def route_tools(intent: ClassifiedIntent, *, conv_tracking_number: str | None = None) -> ToolRoute:
    name = intent.name
    tn = intent.tracking_number or conv_tracking_number

    if name == CopilotIntent.TRACKING_NUMBER_EXACT and tn:
        return ToolRoute(plan=[("get_tracking_by_number", {"tracking_number": tn})])

    if name == CopilotIntent.TRACKING_FOLLOWUP and tn:
        if intent.use_memory_only and intent.follow_up_kind in {"creator", "delay", "duration"}:
            return ToolRoute(plan=[], memory_only=True)
        return ToolRoute(plan=[("get_tracking_by_number", {"tracking_number": tn})])

    if name == CopilotIntent.USER_FOLLOWUP:
        return ToolRoute(plan=[], memory_only=True)

    if name == CopilotIntent.EXPORT_CONTEXTUAL:
        if intent.follow_up_kind == "history_export" and tn:
            return ToolRoute(plan=[], export_module="tracking_history")
        if intent.follow_up_kind == "profile":
            return ToolRoute(plan=[], export_module="users", export_single=True)
        mod = intent.domain if intent.domain in {"users", "notifications", "logs", "tickets", "tracking"} else None
        return ToolRoute(plan=[], export_module=mod or "generic")

    if name == CopilotIntent.PLATFORM_HEALTH_REPORT:
        return ToolRoute(plan=list(_PLATFORM_HEALTH_PLAN))

    if name == CopilotIntent.SECURITY_REPORT:
        return ToolRoute(plan=list(_SECURITY_REPORT_PLAN))

    if name == CopilotIntent.CRITICAL_INCIDENTS:
        return ToolRoute(plan=[("get_security_alerts", {"limit": 30})])

    if name == CopilotIntent.SUSPICIOUS_ACTIVITY:
        return ToolRoute(plan=[
            ("analyze_suspicious_logs", {"hours": 24}),
            ("get_security_alerts", {"limit": 15}),
        ])

    if name == CopilotIntent.TOP_ACTIVE_USERS:
        return ToolRoute(plan=list(_ANALYTICS_USERS_PLAN))

    if name == CopilotIntent.NOTIFICATION_FREQUENCY:
        return ToolRoute(plan=[("get_notifications_summary", {"limit": 50})])

    if name == CopilotIntent.TICKET_QUERY:
        return ToolRoute(plan=[("get_open_tickets", {"status": "open", "limit": 30})])

    if name in {CopilotIntent.USER_LIST, CopilotIntent.LIST_ACTIVE_USERS}:
        args: dict[str, Any] = {"limit": 30}
        if intent.filter_active:
            args["status"] = "active"
        return ToolRoute(plan=[("get_users_summary", args)])

    if name in {CopilotIntent.USER_COUNT, CopilotIntent.COUNT_ACTIVE_USERS}:
        args = {"limit": 50}
        if intent.filter_active:
            args["status"] = "active"
        return ToolRoute(plan=[("get_users_summary", args)])

    if name == CopilotIntent.NOTIFICATION_LIST:
        limit = intent.export_limit or 20
        return ToolRoute(plan=[("get_notifications_summary", {"limit": limit})])

    if name == CopilotIntent.TRACKING_LIST:
        return ToolRoute(plan=[("get_tracking_summary", {"limit": 10})])

    return ToolRoute(plan=[])
