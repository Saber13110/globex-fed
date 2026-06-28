"""Politique d'approbation Globex OS — ordre admin direct vs initiative agent."""

from __future__ import annotations

import re
from typing import Any, Literal

ApprovalMode = Literal["never", "agent_only", "always"]

# never = exécution directe ; agent_only = approbation si initiative agent ;
# always = toujours approbation (même ordre admin explicite).
TOOL_APPROVAL_MODES: dict[str, ApprovalMode] = {
    # Lecture / alertes info
    "get_platform_stats": "never",
    "analyze_tracking": "never",
    "analyze_users": "never",
    "search_users": "never",
    "analyze_notifications": "never",
    "notify_admin": "never",
    "notify_admin_task_complete": "never",
    "push_jarvis_alert": "never",
    "draft_client_email": "never",
    "draft_ticket_reply": "never",
    "scan_ticket_sla": "never",
    "scan_dormant_accounts": "never",
    "get_security_alerts": "never",
    "generate_security_report": "never",
    "analyze_platform_health": "never",
    "analyze_weekly_activity": "never",
    "get_agent_missions_summary": "never",
    "get_workspace_briefing": "never",
    # Actions sensibles — ordre direct autorisé
    "suspend_user": "agent_only",
    "reactivate_user": "agent_only",
    "send_email": "agent_only",
    "send_client_email": "agent_only",
    "send_admin_email": "agent_only",
    "notify_user": "agent_only",
    "notify_user_warning": "agent_only",
    "notify_employee": "agent_only",
    "reply_support_ticket": "agent_only",
    "close_ticket": "agent_only",
    "escalate_ticket": "agent_only",
    "assign_ticket": "agent_only",
    "update_ticket_priority": "agent_only",
    "invite_user": "agent_only",
    # Toujours valider
    "notify_users_by_role": "always",
    "notify_all_users": "always",
    "send_bulk_email": "always",
    "suspend_users_bulk": "always",
    "delete_user": "always",
}

_DIRECT_VERB_RE = re.compile(
    r"^(?:"
    r"suspend(?:s|re)?|suspendez|"
    r"r[eé]activ(?:e|ez|er)|"
    r"envo(?:ie|ye|yer)|send|"
    r"notifi(?:e|ez|er)|"
    r"ferme(?:z)?|close|"
    r"escalade(?:z)?|escalate|"
    r"r[eé]pond(?:s|re|ez)?|reply|"
    r"g[eé]n[eè]r(?:e|ez|er)?|export(?:e|ez|er)?|"
    r"t[eé]l[eé]charg(?:e|ez|er)?|"
    r"interromp(?:s|ez)?|bloque(?:z)?|lock"
    r")\b",
    re.I,
)
_EXPORT_EXPLICIT_RE = re.compile(
    r"\b("
    r"tu\s+peu[xs]?|peu[xs][- ]tu|"
    r"g[eé]n[eè]r|export|exporter|rapport|fichier|"
    r"t[eé]l[eé]charg|mets?.{0,10}en"
    r").{0,50}\b(pdf|excel|xlsx|logs?|journaux)\b",
    re.I,
)

_TOOL_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsuspend", re.I), "suspend_user"),
    (re.compile(r"\br[eé]activ", re.I), "reactivate_user"),
    (re.compile(r"\b(?:envo(?:ie|ye|yer)|send).{0,40}(?:mail|email|e-mail)", re.I), "send_client_email"),
    (re.compile(r"\b(?:envo(?:ie|ye|yer)|send).{0,60}(?:une\s+)?notifications?", re.I), "notify_user"),
    (re.compile(r"\bnotifi(?:e|ez|er|cation)", re.I), "notify_user"),
    (re.compile(r"\bferme(?:z)?\s+(?:le\s+)?ticket", re.I), "close_ticket"),
    (re.compile(r"\bescalade(?:z)?", re.I), "escalate_ticket"),
    (re.compile(r"\br[eé]pond(?:s|re|ez)?\s+(?:au\s+)?ticket", re.I), "reply_support_ticket"),
]


def detect_admin_direct_order(message: str) -> bool:
    """True si l'admin donne un ordre impératif (Cas 1 / Niveau 3)."""
    text = (message or "").strip()
    if len(text) < 4:
        return False
    if _EXPORT_EXPLICIT_RE.search(text):
        return True
    if _DIRECT_VERB_RE.search(text):
        return True
    if re.search(r"\b(fais|fais-le|exécute|execute|lance|do it)\b", text, re.I):
        return True
    return False


def infer_direct_tool(message: str) -> str | None:
    """Outil probable pour un ordre admin direct (planification déterministe)."""
    text = message or ""
    for pattern, tool in _TOOL_HINTS:
        if pattern.search(text):
            return tool
    return None


def approval_mode_for_tool(tool_name: str) -> ApprovalMode:
    if tool_name in TOOL_APPROVAL_MODES:
        return TOOL_APPROVAL_MODES[tool_name]
    from app.services.gpt.tool_registry import get_tool

    defn = get_tool(tool_name)
    if defn is None:
        return "agent_only"
    if defn.is_read_tool:
        return "never"
    if defn.requires_approval or defn.sensitivity == "destructive":
        return "agent_only"
    if defn.sensitivity == "write":
        return "agent_only"
    return "never"


def should_require_approval(
    tool_name: str,
    *,
    admin_direct_order: bool = False,
    agent_initiated: bool = True,
) -> bool:
    """Décide si l'outil doit passer par une carte d'approbation."""
    mode = approval_mode_for_tool(tool_name)
    if mode == "never":
        return False
    if mode == "always":
        return True
    # agent_only
    if admin_direct_order and not agent_initiated:
        return False
    if admin_direct_order:
        return False
    return True


def approval_hint_for(tool_name: str, args: dict[str, Any]) -> str:
    try:
        hours = int(args.get("hours") or 24)
    except (TypeError, ValueError):
        hours = 24
    if tool_name in {"export_activity_logs_pdf", "export_activity_logs_excel"}:
        fmt = "Excel" if "excel" in tool_name else "PDF"
        period = f"{hours // 24} jour(s)" if hours >= 24 and hours % 24 == 0 else f"{hours} h"
        return f"Générer un export **{fmt}** des journaux sur **{period}** ?"
    if tool_name.startswith("export_"):
        return "Préparer l'export demandé ?"
    if tool_name == "suspend_user":
        email = args.get("email") or "cet utilisateur"
        return f"Suspendre le compte **{email}** ?"
    if tool_name == "notify_user":
        return "Envoyer la notification au client ?"
    if tool_name in {"send_client_email", "send_email"}:
        return "Envoyer cet e-mail ?"
    return "Confirmer cette action sensible ?"
