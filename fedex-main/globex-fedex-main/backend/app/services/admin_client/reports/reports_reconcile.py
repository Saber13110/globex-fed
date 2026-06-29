"""Reconcile plan reports — paramètres message + routeur."""

from __future__ import annotations

import re

from app.services.admin_client.reports.reports_intent import (
    _extract_format_filter,
    _extract_recipient_query,
    _extract_run_id,
    _extract_slug_hint,
)
from app.services.admin_client.reports.reports_types import (
    ReportsPlan,
    ReportsProfile,
    ReportsTaskType,
)
from app.services.admin_client.reports.reports_workspace import normalize_reports_text

_LATEST_RE = re.compile(r"\b(dernier|last|recent|r[eé]cent)\b", re.I)
_SEARCH_STOP = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "et",
        "ou",
        "rapport",
        "rapports",
        "report",
        "reports",
        "export",
        "exports",
        "liste",
        "list",
        "montre",
        "affiche",
        "donne",
        "moi",
        "tous",
        "all",
        "recent",
        "recents",
        "recente",
        "recentes",
        "dernier",
        "derniers",
        "excel",
        "xlsx",
        "csv",
        "json",
        "previsualise",
        "previsualiser",
        "prevusu",
        "accord",
        "que",
        "tu",
        "je",
        "veux",
        "daccord",
    }
)

_PROFILE_FOR_TASK = {
    ReportsTaskType.report_preview: ReportsProfile.PREVIEW,
    ReportsTaskType.report_list_recent: ReportsProfile.LIST,
    ReportsTaskType.report_redownload: ReportsProfile.DOWNLOAD,
    ReportsTaskType.report_share: ReportsProfile.SHARE_PROMPT,
}


def _extract_search_filter(text: str, slug_hint: str | None) -> str | None:
    if slug_hint:
        return slug_hint.replace("-", " ")
    norm = normalize_reports_text(text)
    tokens = [t for t in re.findall(r"[a-z0-9]+", norm) if t not in _SEARCH_STOP and len(t) > 2]
    if len(tokens) >= 2:
        return " ".join(tokens[:4])
    if tokens:
        return tokens[0]
    return None


def reconcile_reports_plan(
    message: str, plan: ReportsPlan, *, history_text: str = ""
) -> ReportsPlan:
    text = normalize_reports_text(message)

    run_id = plan.run_id or _extract_run_id(text, history_text=history_text)
    if run_id:
        plan.run_id = run_id
        plan.run_selector = "by_id"
    elif _LATEST_RE.search(text):
        plan.run_selector = "latest"

    if not plan.format_filter:
        plan.format_filter = _extract_format_filter(text)
    if not plan.slug_hint:
        plan.slug_hint = _extract_slug_hint(text)

    if plan.task_type == ReportsTaskType.report_list_recent and not plan.search_filter:
        plan.search_filter = _extract_search_filter(text, plan.slug_hint)
    elif plan.task_type != ReportsTaskType.report_list_recent:
        plan.search_filter = None

    if plan.task_type == ReportsTaskType.report_share and not plan.recipient_query:
        plan.recipient_query = _extract_recipient_query(message)

    if plan.profile == ReportsProfile.LIST and plan.task_type != ReportsTaskType.report_list_recent:
        plan.profile = _PROFILE_FOR_TASK.get(plan.task_type, plan.profile)
    elif plan.task_type in _PROFILE_FOR_TASK and plan.profile == ReportsProfile.LIST:
        plan.profile = _PROFILE_FOR_TASK[plan.task_type]

    return plan
