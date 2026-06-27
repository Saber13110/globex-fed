"""Catalogue Globex OS — 62 outils admin avec métadonnées phase/groupe."""

from __future__ import annotations

from typing import Any

from app.services.globex_agent.approval_policy import approval_mode_for_tool
from app.services.gpt.tool_handlers import HANDLERS
from app.services.gpt.tool_registry import TOOL_DEFINITIONS, get_tool

CATALOG_TARGET_COUNT = 62

# phase: 0=fondations, 1=socle, 2=tickets, 3=broadcast, 4=proactif, 5=catalogue
_TOOL_META: dict[str, dict[str, str]] = {
    "get_platform_stats": {"phase": "1", "group": "analytics"},
    "analyze_tracking": {"phase": "1", "group": "analytics"},
    "analyze_tickets": {"phase": "2", "group": "tickets"},
    "analyze_users": {"phase": "1", "group": "users"},
    "analyze_logs": {"phase": "1", "group": "security"},
    "analyze_notifications": {"phase": "1", "group": "analytics"},
    "analyze_conversations": {"phase": "1", "group": "analytics"},
    "search_knowledge": {"phase": "1", "group": "knowledge"},
    "list_knowledge_documents": {"phase": "1", "group": "knowledge"},
    "analyze_reports": {"phase": "1", "group": "analytics"},
    "analyze_security": {"phase": "1", "group": "security"},
    "get_security_alerts": {"phase": "5", "group": "security"},
    "generate_security_report": {"phase": "5", "group": "security"},
    "analyze_platform_health": {"phase": "5", "group": "analytics"},
    "analyze_weekly_activity": {"phase": "5", "group": "analytics"},
    "get_workspace_briefing": {"phase": "5", "group": "workspace"},
    "export_activity_logs_pdf": {"phase": "1", "group": "exports"},
    "export_activity_logs_excel": {"phase": "1", "group": "exports"},
    "export_notifications_pdf": {"phase": "1", "group": "exports"},
    "export_tracking_pdf": {"phase": "1", "group": "exports"},
    "export_users_pdf": {"phase": "1", "group": "exports"},
    "export_tickets_pdf": {"phase": "1", "group": "exports"},
    "export_conversations_pdf": {"phase": "1", "group": "exports"},
    "export_generic_result_pdf": {"phase": "1", "group": "exports"},
    "generate_text_pdf": {"phase": "1", "group": "exports"},
    "fedex_track_package": {"phase": "0", "group": "fedex"},
    "get_tracking_by_number": {"phase": "0", "group": "fedex"},
    "find_fedex_location": {"phase": "0", "group": "fedex"},
    "get_admin_users": {"phase": "1", "group": "users"},
    "analyze_suspicious_logs": {"phase": "1", "group": "security"},
    "suspend_user": {"phase": "1", "group": "users"},
    "reactivate_user": {"phase": "1", "group": "users"},
    "delete_user": {"phase": "5", "group": "users"},
    "invite_user": {"phase": "5", "group": "users"},
    "search_users": {"phase": "1", "group": "users"},
    "scan_dormant_accounts": {"phase": "3", "group": "users"},
    "suspend_users_bulk": {"phase": "3", "group": "users"},
    "create_ticket": {"phase": "2", "group": "tickets"},
    "reply_support_ticket": {"phase": "2", "group": "tickets"},
    "close_ticket": {"phase": "2", "group": "tickets"},
    "escalate_ticket": {"phase": "2", "group": "tickets"},
    "draft_ticket_reply": {"phase": "2", "group": "tickets"},
    "scan_ticket_sla": {"phase": "2", "group": "tickets"},
    "assign_ticket": {"phase": "5", "group": "tickets"},
    "update_ticket_priority": {"phase": "5", "group": "tickets"},
    "send_notification": {"phase": "1", "group": "communication"},
    "notify_admin": {"phase": "0", "group": "communication"},
    "notify_admin_task_complete": {"phase": "5", "group": "communication"},
    "push_jarvis_alert": {"phase": "5", "group": "workspace"},
    "notify_user": {"phase": "1", "group": "communication"},
    "notify_user_warning": {"phase": "5", "group": "communication"},
    "notify_employee": {"phase": "1", "group": "communication"},
    "notify_users_by_role": {"phase": "3", "group": "communication"},
    "notify_all_users": {"phase": "3", "group": "communication"},
    "send_email": {"phase": "1", "group": "communication"},
    "send_client_email": {"phase": "1", "group": "communication"},
    "send_admin_email": {"phase": "5", "group": "communication"},
    "send_bulk_email": {"phase": "3", "group": "communication"},
    "draft_client_email": {"phase": "1", "group": "communication"},
    "run_security_scan": {"phase": "1", "group": "security"},
    "create_agent_mission": {"phase": "0", "group": "agent"},
    "get_agent_missions_summary": {"phase": "5", "group": "agent"},
}


def build_tool_catalog() -> list[dict[str, Any]]:
    """Liste complète des outils avec handler, approbation et métadonnées."""
    items: list[dict[str, Any]] = []
    for tool in TOOL_DEFINITIONS:
        meta = _TOOL_META.get(tool.name, {"phase": "5", "group": "other"})
        items.append(
            {
                "name": tool.name,
                "description": tool.description[:300],
                "sensitivity": tool.sensitivity,
                "requires_approval": tool.requires_approval,
                "is_read_tool": tool.is_read_tool,
                "approval_mode": approval_mode_for_tool(tool.name),
                "phase": meta["phase"],
                "group": meta["group"],
                "has_handler": tool.name in HANDLERS,
            }
        )
    return items


def catalog_summary() -> dict[str, Any]:
    catalog = build_tool_catalog()
    groups: dict[str, int] = {}
    phases: dict[str, int] = {}
    for item in catalog:
        groups[item["group"]] = groups.get(item["group"], 0) + 1
        phases[item["phase"]] = phases.get(item["phase"], 0) + 1
    missing_handlers = [i["name"] for i in catalog if not i["has_handler"]]
    return {
        "target_count": CATALOG_TARGET_COUNT,
        "registered_count": len(catalog),
        "complete": len(catalog) >= CATALOG_TARGET_COUNT and not missing_handlers,
        "groups": groups,
        "phases": phases,
        "missing_handlers": missing_handlers,
    }


def assert_catalog_complete() -> None:
    catalog = build_tool_catalog()
    if len(catalog) < CATALOG_TARGET_COUNT:
        raise AssertionError(f"Catalogue incomplet: {len(catalog)}/{CATALOG_TARGET_COUNT}")
    missing = [t.name for t in TOOL_DEFINITIONS if t.name not in HANDLERS]
    if missing:
        raise AssertionError(f"Handlers manquants: {missing}")
    for name in HANDLERS:
        if get_tool(name) is None:
            raise AssertionError(f"Handler orphelin sans définition: {name}")
