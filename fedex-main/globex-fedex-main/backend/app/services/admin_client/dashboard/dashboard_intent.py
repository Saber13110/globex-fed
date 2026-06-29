"""Classification intents dashboard admin — familles regex + reconcile."""

from __future__ import annotations

import re
from typing import Any

from app.services.admin_client.dashboard.dashboard_signals import (
    is_grey_zone,
    pick_top_signal,
    score_dashboard_signals,
    signal_to_task_type,
)
from app.services.admin_client.dashboard.dashboard_types import (
    DashboardPlan,
    DashboardQuestionType,
    DashboardTaskType,
)
from app.services.admin_client.dashboard.dashboard_workspace import is_dashboard_workspace

_VALID_PERIODS = frozenset({"today", "week", "month"})

# Re-export for backward compatibility
__all__ = [
    "DashboardPlan",
    "DashboardQuestionType",
    "DashboardTaskType",
    "classify_dashboard_intent",
    "plan_from_router_data",
]
_DELAY_REPORT_RE = re.compile(
    r"\b(rapport\s+(des\s+)?retards?|delay\s+report|prepare\s+.*report.*delay)\b",
    re.I,
)
_DELAY_LIST_RE = re.compile(
    r"\b("
    r"retards?|delayed|probl[eé]matiques?|at\s+risk|"
    r"colis\s+en\s+(retard|souffrance)|shipments?\s+delayed"
    r")\b",
    re.I,
)
_NEW_USERS_RE = re.compile(
    r"\b("
    r"nouveaux?\s+utilisateurs?|new\s+users?|utilisateurs?\s+cr[eé][eé]s?|"
    r"users?\s+created|inscriptions?\s+r[eé]centes?"
    r")\b",
    re.I,
)
_USERS_BREAKDOWN_RE = re.compile(
    r"\b("
    r"utilisateurs?\s+par\s+r[oô]le|users?\s+by\s+role|r[eé]partition\s+(des\s+)?comptes|"
    r"breakdown\s+users?|r[oô]les?\s+et\s+statuts?"
    r")\b",
    re.I,
)
_AUDIT_RE = re.compile(
    r"\b("
    r"audit|journaux?|logs?\s+admin|activit[eé]\s+suspecte?|suspicious|"
    r"anomal|intrusion|ids|s[eé]curit[eé]\s+aujourd"
    r")\b",
    re.I,
)
_CONVERSATIONS_RE = re.compile(
    r"\b(conversations?\s+ia|ai\s+conversations?|chats?\s+assistant|recent\s+conversations?)\b",
    re.I,
)
_ACTIVITY_RE = re.compile(
    r"\b(activit[eé]\s+r[eé]cente|recent\s+activity|timeline|what\s+happened)\b",
    re.I,
)
_OVERVIEW_RE = re.compile(
    r"\b("
    r"[eé]tat\s+(de\s+la\s+)?plateforme|platform\s+(status|overview|health)|"
    r"r[eé]sum[eé]\s+(de\s+la\s+)?plateforme|platform\s+summary|"
    r"kpi|tableau\s+de\s+bord|dashboard|situation\s+globale|"
    r"aujourd[\u2019']hui|today[\u2019]s?\s+status"
    r")\b",
    re.I,
)
_PERIOD_TODAY_RE = re.compile(r"\baujourd[\u2019']hui\b|\btoday\b", re.I)
_PERIOD_WEEK_RE = re.compile(
    r"\b(cette\s+semaine|this\s+week|7\s+jours|seven\s+days)\b", re.I
)
_PERIOD_MONTH_RE = re.compile(r"\b(ce\s+mois|this\s+month|30\s+jours)\b", re.I)
_CHARTS_RE = re.compile(r"\b(graphique|chart|visualis)\b", re.I)
_PDF_RE = re.compile(r"\b(pdf|exporte?|t[eé]l[eé]charge)\b", re.I)
_ROLE_CLIENT_RE = re.compile(r"\bclients?\b", re.I)
_ROLE_EMPLOYE_RE = re.compile(r"\b(employ[eé]s?|employees?)\b", re.I)
_ROLE_ADMIN_RE = re.compile(
    r"\b(r[oô]le\s+)?admins?\b(?!\s*(logs?|journal|audit))|"
    r"\badministrateurs?\b",
    re.I,
)
_LIMIT_RE = re.compile(r"\b(\d{1,2})\s+(premiers?|first|top)\b", re.I)


def _extract_period(text: str) -> str:
    if _PERIOD_TODAY_RE.search(text):
        return "today"
    if _PERIOD_MONTH_RE.search(text):
        return "month"
    if _PERIOD_WEEK_RE.search(text):
        return "week"
    return "today"


def _extract_role(text: str) -> str:
    if _ROLE_ADMIN_RE.search(text):
        return "admin"
    if _ROLE_EMPLOYE_RE.search(text):
        return "employe"
    if _ROLE_CLIENT_RE.search(text):
        return "client"
    return "all"


def _extract_limit(text: str, default: int = 10) -> int:
    m = _LIMIT_RE.search(text)
    if m:
        return min(max(int(m.group(1)), 1), 50)
    return default


def _match_families(text: str) -> list[tuple[DashboardTaskType, str]]:
    matches: list[tuple[DashboardTaskType, str]] = []
    if _DELAY_REPORT_RE.search(text):
        matches.append((DashboardTaskType.quick_delay_report, "delay_report"))
    if _DELAY_LIST_RE.search(text):
        matches.append((DashboardTaskType.delayed_shipments, "delays"))
    if _NEW_USERS_RE.search(text):
        matches.append((DashboardTaskType.new_users_period, "new_users"))
    if _USERS_BREAKDOWN_RE.search(text):
        matches.append((DashboardTaskType.users_breakdown, "users_breakdown"))
    if _AUDIT_RE.search(text):
        matches.append((DashboardTaskType.recent_audit, "audit"))
    if _CONVERSATIONS_RE.search(text):
        matches.append((DashboardTaskType.recent_ai_conversations, "conversations"))
    if _ACTIVITY_RE.search(text):
        matches.append((DashboardTaskType.recent_activity, "activity"))
    if _OVERVIEW_RE.search(text):
        matches.append((DashboardTaskType.platform_overview, "overview"))
    return matches


_PRIORITY = (
    DashboardTaskType.quick_delay_report,
    DashboardTaskType.delayed_shipments,
    DashboardTaskType.new_users_period,
    DashboardTaskType.users_breakdown,
    DashboardTaskType.recent_audit,
    DashboardTaskType.recent_ai_conversations,
    DashboardTaskType.recent_activity,
    DashboardTaskType.platform_overview,
)


_VAGUE_DASHBOARD_RE = re.compile(
    r"^(montre|show|dis|tell|aide|help|explique|explain)\b", re.I
)


def classify_dashboard_intent(message: str) -> DashboardPlan:
    text = (message or "").strip()
    if not is_dashboard_workspace(text):
        return DashboardPlan(task_type=DashboardTaskType.ambiguous)

    scores = score_dashboard_signals(text)
    top_signal, top_score, _second = pick_top_signal(scores)

    matches = _match_families(text)
    if matches:
        matched_types = {m[0] for m in matches}
        task = DashboardTaskType.ambiguous
        for candidate in _PRIORITY:
            if candidate in matched_types:
                task = candidate
                break
    elif top_signal:
        try:
            task = DashboardTaskType(signal_to_task_type(top_signal))
        except ValueError:
            task = DashboardTaskType.platform_overview
    elif is_grey_zone(scores):
        return DashboardPlan(
            task_type=DashboardTaskType.ambiguous,
            signal_scores=scores,
            needs_router=True,
        )
    elif _VAGUE_DASHBOARD_RE.search(text) and not _OVERVIEW_RE.search(text):
        return DashboardPlan(
            task_type=DashboardTaskType.ambiguous,
            signal_scores=scores,
            needs_router=True,
        )
    else:
        return DashboardPlan(
            task_type=DashboardTaskType.ambiguous,
            signal_scores=scores,
        )

    suspicious = bool(
        re.search(r"\b(suspecte?|anomal|intrusion|ids)\b", text, re.I)
    )

    plan = DashboardPlan(
        task_type=task,
        period=_extract_period(text),
        role=_extract_role(text),
        status="all",
        limit=_extract_limit(text),
        suspicious_only=suspicious and task == DashboardTaskType.recent_audit,
        include_charts=bool(_CHARTS_RE.search(text) or task == DashboardTaskType.quick_delay_report),
        include_pdf=bool(_PDF_RE.search(text) or task == DashboardTaskType.quick_delay_report),
        raw_matches=[m[1] for m in matches] if matches else ([top_signal] if top_signal else []),
        signal_scores=scores,
    )
    if top_signal == "health":
        plan.question_type = DashboardQuestionType.STATUS
    elif top_signal == "kpi_advisory":
        plan.question_type = DashboardQuestionType.KPI_LIST
    elif top_signal == "explain":
        plan.question_type = DashboardQuestionType.EXPLAIN
    from app.services.admin_client.dashboard.dashboard_reconcile import reconcile_dashboard_plan

    return reconcile_dashboard_plan(text, plan)


def plan_from_router_data(data: dict[str, Any]) -> DashboardPlan | None:
    """Convertit JSON routeur Ollama en DashboardPlan."""
    task_raw = str(data.get("task_type") or "").strip()
    try:
        task = DashboardTaskType(task_raw)
    except ValueError:
        return None
    if task == DashboardTaskType.ambiguous:
        return None

    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    period = str(answers.get("period") or "today").lower()
    if period not in _VALID_PERIODS:
        period = "today"
    role = str(answers.get("role") or "all").lower()
    limit = min(max(int(answers.get("limit") or 10), 1), 50)

    return DashboardPlan(
        task_type=task,
        period=period,
        role=role if role in ("client", "employe", "admin", "all") else "all",
        limit=limit,
        suspicious_only=bool(answers.get("suspicious_only")),
        include_charts=bool(answers.get("include_charts")),
        include_pdf=bool(answers.get("include_pdf")),
    )
