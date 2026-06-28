"""Registre outils entreprise — alias vers handlers GPT existants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Alias entreprise → handler backend existant
TOOL_ALIASES: dict[str, str] = {
    "get_platform_stats": "get_platform_stats",
    "get_tracking_summary": "analyze_tracking",
    "get_tracking_by_number": "get_tracking_by_number",
    "get_admin_users": "get_admin_users",
    "analyze_suspicious_logs": "analyze_suspicious_logs",
    "export_logs_pdf": "export_activity_logs_pdf",
    "get_recent_trackings": "analyze_tracking",
    "get_notifications_summary": "analyze_notifications",
    "get_unread_notifications": "analyze_notifications",
    "get_users_summary": "analyze_users",
    "get_active_users": "analyze_users",
    "get_security_alerts": "analyze_security",
    "get_security_score": "analyze_security",
    "get_recent_logs": "analyze_logs",
    "get_logs_analysis": "analyze_logs",
    "get_open_tickets": "analyze_tickets",
    "get_tickets_summary": "analyze_tickets",
    "get_conversations_summary": "analyze_conversations",
    "get_reports_summary": "analyze_reports",
    "get_agent_missions_summary": "create_agent_mission",
    "search_knowledge_base": "search_knowledge",
    "search_database_context": "search_knowledge",
    "get_agent_missions_summary": "get_agent_missions_summary",
    "analyze_weekly_activity": "analyze_logs",
    "analyze_platform_health": "analyze_platform_health",
    "generate_security_report": "generate_security_report",
    "platform_health_report": "platform_health_report",
    # Legacy names (compat)
    "analyze_tracking": "analyze_tracking",
    "analyze_notifications": "analyze_notifications",
    "analyze_users": "analyze_users",
    "analyze_logs": "analyze_logs",
    "analyze_tickets": "analyze_tickets",
    "analyze_conversations": "analyze_conversations",
    "analyze_security": "analyze_security",
    "analyze_reports": "analyze_reports",
    "search_knowledge": "search_knowledge",
}


@dataclass(frozen=True)
class EnterpriseToolSpec:
    name: str
    handler: str
    description: str
    default_args: dict[str, Any]


ENTERPRISE_TOOLS: list[EnterpriseToolSpec] = [
    EnterpriseToolSpec(
        "get_platform_stats", "get_platform_stats",
        "KPIs temps réel : utilisateurs, expéditions, incidents, requêtes FedEx.", {},
    ),
    EnterpriseToolSpec(
        "get_tracking_summary", "analyze_tracking",
        "Résumé expéditions/colis : statuts, retards, volumes récents.", {"limit": 30},
    ),
    EnterpriseToolSpec(
        "get_recent_trackings", "analyze_tracking",
        "Derniers colis suivis en base.", {"limit": 20},
    ),
    EnterpriseToolSpec(
        "get_tracking_by_number", "fedex_track_package",
        "Suivi FedEx d'un numéro de colis.", {},
    ),
    EnterpriseToolSpec(
        "get_notifications_summary", "analyze_notifications",
        "Résumé notifications plateforme.", {"limit": 20},
    ),
    EnterpriseToolSpec(
        "get_unread_notifications", "analyze_notifications",
        "Notifications non lues.", {"limit": 30, "unread_only": True},
    ),
    EnterpriseToolSpec(
        "get_users_summary", "analyze_users",
        "Statistiques et liste comptes utilisateurs.", {"limit": 50},
    ),
    EnterpriseToolSpec(
        "get_active_users", "analyze_users",
        "Utilisateurs actifs.", {"limit": 50, "status": "active"},
    ),
    EnterpriseToolSpec(
        "get_security_alerts", "analyze_security",
        "Alertes et incidents sécurité (IDS, tentatives).", {},
    ),
    EnterpriseToolSpec(
        "get_security_score", "analyze_security",
        "Score et état sécurité plateforme.", {},
    ),
    EnterpriseToolSpec(
        "get_recent_logs", "analyze_logs",
        "Derniers journaux d'activité.", {"hours": 24, "limit": 30},
    ),
    EnterpriseToolSpec(
        "get_logs_analysis", "analyze_logs",
        "Analyse logs sur période.", {"hours": 168, "limit": 50},
    ),
    EnterpriseToolSpec(
        "get_open_tickets", "analyze_tickets",
        "Tickets support ouverts.", {"status": "open", "limit": 30},
    ),
    EnterpriseToolSpec(
        "get_tickets_summary", "analyze_tickets",
        "Résumé tickets support.", {"status": "all", "limit": 30},
    ),
    EnterpriseToolSpec(
        "get_conversations_summary", "analyze_conversations",
        "Conversations chat récentes.", {"limit": 40},
    ),
    EnterpriseToolSpec(
        "get_reports_summary", "analyze_reports",
        "Rapports et exports disponibles.", {},
    ),
    EnterpriseToolSpec(
        "search_knowledge_base", "search_knowledge",
        "Recherche sémantique base de connaissances GPT.", {"limit": 8},
    ),
    EnterpriseToolSpec(
        "analyze_weekly_activity", "analyze_logs",
        "Activité plateforme sur 7 jours (logs agrégés).", {"hours": 168, "limit": 60},
    ),
    EnterpriseToolSpec(
        "analyze_platform_health", "get_platform_stats",
        "Santé globale plateforme (KPIs + indicateurs).", {},
    ),
]

_TOOL_MAP = {t.name: t for t in ENTERPRISE_TOOLS}


def resolve_handler(tool_name: str) -> str:
    return TOOL_ALIASES.get(tool_name, tool_name)


def get_tool_spec(tool_name: str) -> EnterpriseToolSpec | None:
    return _TOOL_MAP.get(tool_name)


def list_enterprise_tool_names() -> list[str]:
    return [t.name for t in ENTERPRISE_TOOLS]


def default_args_for(tool_name: str) -> dict[str, Any]:
    spec = get_tool_spec(tool_name)
    return dict(spec.default_args) if spec else {}
