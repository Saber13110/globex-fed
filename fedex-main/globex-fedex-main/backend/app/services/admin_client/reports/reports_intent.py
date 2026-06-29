"""Classification intents centre de rapports admin."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.services.admin_client.reports.reports_types import (
    ReportsPlan,
    ReportsProfile,
    ReportsTaskType,
)
from app.services.admin_client.reports.reports_followup import (
    extract_report_run_ref,
    is_reports_followup_message,
    is_reports_history_context,
)
from app.services.admin_client.reports.reports_workspace import (
    is_reports_grey_zone,
    is_reports_workspace,
    normalize_reports_text,
)

from app.services.reports_service import REPORT_CATALOG

_PREVIEW_RE = re.compile(
    r"\b(previsualis\w*|pr[eé]v\w+|preview|aper[cç]u|montre.*contenu|voir.*contenu|"
    r"consulte[rz]?|d[eé]tails?|infos?)\b",
    re.I,
)
_REDOWNLOAD_RE = re.compile(
    r"\b(re[- ]?t[eé]l[eé]charg|t[eé]l[eé]charge|telecharg|redownload|ret[eé]l[eé]charg|"
    r"t[eé]l[eé]charge[rz]?\s+(le\s+)?(dernier\s+)?(export|rapport|report|#\s*\d+)|"
    r"download\s+(the\s+)?(last\s+)?(export|report|#\s*\d+)|"
    r"t[eé]l[eé]charge[rz]?\s+.{0,20}(rapport|report|#\s*\d+))\b",
    re.I,
)
_SHARE_RE = re.compile(
    r"\b(partage[rz]?|share|envo(?:ie|ye|yer)|send)\s+.{0,30}(rapport|report|export)\b",
    re.I,
)
_LIST_RE = re.compile(
    r"\b("
    r"exports?\s+r[eé]cents?|recent\s+exports?|"
    r"liste.{0,30}(rapports?|reports?|exports?)|"
    r"list.{0,30}(rapports?|reports?|exports?)|"
    r"(tous les|all)\s+(les\s+)?(rapports?|reports?|exports?)|"
    r"liste\s+(des\s+)?rapports?|list\s+reports?|"
    r"derniers?\s+rapports?|historique\s+exports?|"
    r"montre.{0,20}(rapports?|reports?|exports?)"
    r")\b",
    re.I,
)
_LATEST_RE = re.compile(r"\b(dernier|last|recent|r[eé]cent)\b", re.I)
_RUN_ID_RE = re.compile(r"\b(?:rapport|report|run)\s*#?\s*(\d{1,8})\b", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_FORMAT_RE = re.compile(
    r"\b(excel|xlsx|csv|json|pdf|word|docx)\b",
    re.I,
)
_BARE_REPORTS_RE = re.compile(r"^\s*reports?\s*$", re.I)

_VALID_FORMATS = frozenset({"xlsx", "csv", "json", "pdf"})

_PROFILE_FOR_TASK = {
    ReportsTaskType.report_preview: ReportsProfile.PREVIEW,
    ReportsTaskType.report_list_recent: ReportsProfile.LIST,
    ReportsTaskType.report_redownload: ReportsProfile.DOWNLOAD,
    ReportsTaskType.report_share: ReportsProfile.SHARE_PROMPT,
}


def _extract_format_filter(text: str) -> str | None:
    m = _FORMAT_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token in {"excel", "xlsx"}:
        return "xlsx"
    if token in {"word", "docx"}:
        return "pdf"
    return token


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _extract_run_id(text: str, *, history_text: str = "") -> int | None:
    from app.services.admin_client.reports.reports_followup import extract_report_run_ref

    ref = extract_report_run_ref(text, history_text=history_text)
    if ref is not None:
        return ref
    m = _RUN_ID_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _extract_recipient_query(text: str) -> str:
    emails = _EMAIL_RE.findall(text)
    if emails:
        return emails[0]
    m = re.search(r"\b(?:à|to|pour|for)\s+([^\s,?!.]+)", text, re.I)
    return (m.group(1) if m else "").strip()


def _extract_slug_hint(text: str) -> str | None:
    norm = text.lower()
    for spec in REPORT_CATALOG:
        name = spec["name"].lower()
        slug = spec["slug"]
        slug_words = slug.replace("-", " ")
        if name in norm or slug_words in norm or slug in norm:
            return slug
    return None


def default_clarify_question(lang: str) -> str:
    if lang == "en":
        return (
            "Would you like to list recent exports, preview a report, download one, "
            "or share it by email?"
        )
    return (
        "Voulez-vous lister les exports récents, prévisualiser un rapport, "
        "le télécharger ou le partager par e-mail ?"
    )


def clarify_plan_from_router(data: dict[str, Any]) -> ReportsPlan:
    question = str(data.get("clarification_question") or "").strip()
    return ReportsPlan(
        task_type=ReportsTaskType.ambiguous,
        profile=ReportsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=question,
        raw_matches=["router_clarify"],
    )


def default_clarify_plan(lang: str) -> ReportsPlan:
    return ReportsPlan(
        task_type=ReportsTaskType.ambiguous,
        profile=ReportsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=default_clarify_question(lang),
        raw_matches=["default_clarify"],
    )


def plan_from_router_data(data: dict[str, Any]) -> ReportsPlan | None:
    """Convertit JSON routeur Ollama en ReportsPlan."""
    task_raw = str(data.get("task_type") or "").strip()
    try:
        task = ReportsTaskType(task_raw)
    except ValueError:
        return None
    if task == ReportsTaskType.ambiguous:
        return None

    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    run_id = answers.get("run_id")
    parsed_run_id: int | None = None
    if run_id is not None:
        try:
            parsed_run_id = int(run_id)
        except (TypeError, ValueError):
            parsed_run_id = None

    fmt = str(answers.get("format_filter") or "").strip().lower() or None
    if fmt and fmt not in _VALID_FORMATS:
        fmt = None

    slug = str(answers.get("slug_hint") or "").strip() or None
    recipient = str(answers.get("recipient_query") or "").strip()

    return ReportsPlan(
        task_type=task,
        run_id=parsed_run_id,
        run_selector="by_id" if parsed_run_id else "latest",
        format_filter=fmt,
        slug_hint=slug,
        recipient_query=recipient,
        profile=_PROFILE_FOR_TASK.get(task, ReportsProfile.LIST),
        raw_matches=["router"],
    )


def classify_reports_intent(message: str, *, history_text: str = "") -> ReportsPlan:
    from app.services.admin_client.email.email_patterns import is_send_user_email_message

    if is_send_user_email_message(message):
        return ReportsPlan(task_type=ReportsTaskType.ambiguous, raw_matches=["defer_user_email"])

    text = _normalize(message)
    if not is_reports_workspace(text, history_text=history_text):
        if not is_reports_followup_message(text, history_text=history_text):
            return ReportsPlan(task_type=ReportsTaskType.ambiguous)

    if _BARE_REPORTS_RE.match(text):
        return ReportsPlan(
            task_type=ReportsTaskType.ambiguous,
            needs_router=True,
            raw_matches=["bare_reports"],
        )

    run_id = _extract_run_id(text, history_text=history_text)
    selector = "by_id" if run_id else ("latest" if _LATEST_RE.search(text) else "latest")
    fmt = _extract_format_filter(text)
    slug_hint = _extract_slug_hint(text)

    base_kwargs = dict(
        run_id=run_id,
        run_selector=selector,
        format_filter=fmt,
        slug_hint=slug_hint,
    )

    if is_reports_followup_message(text, history_text=history_text):
        if re.search(r"\b(t[eé]l[eé]charg|telecharg|download)\b", text, re.I):
            return ReportsPlan(
                task_type=ReportsTaskType.report_redownload,
                profile=ReportsProfile.DOWNLOAD,
                raw_matches=["followup_download"],
                **base_kwargs,
            )
        if re.search(r"\b(previsualis|pr[eé]v|prev|aper[cç]u|consulte|voir)\w*\b", text, re.I):
            return ReportsPlan(
                task_type=ReportsTaskType.report_preview,
                profile=ReportsProfile.PREVIEW,
                raw_matches=["followup_preview"],
                **base_kwargs,
            )

    if _SHARE_RE.search(text):
        return ReportsPlan(
            task_type=ReportsTaskType.report_share,
            recipient_query=_extract_recipient_query(message),
            profile=ReportsProfile.SHARE_PROMPT,
            raw_matches=["share"],
            **base_kwargs,
        )
    if _PREVIEW_RE.search(text) or (
        is_reports_followup_message(text, history_text=history_text)
        and re.search(r"\b(pr[eé]v|prev|aper[cç]u|consulte|voir|montre)\b", text, re.I)
    ):
        return ReportsPlan(
            task_type=ReportsTaskType.report_preview,
            profile=ReportsProfile.PREVIEW,
            raw_matches=["preview"],
            **base_kwargs,
        )
    if _REDOWNLOAD_RE.search(text) or (
        is_reports_history_context(history_text)
        and re.search(r"\b(t[eé]l[eé]charg|telecharg|download)\b", text, re.I)
        and extract_report_run_ref(text, history_text=history_text)
    ):
        return ReportsPlan(
            task_type=ReportsTaskType.report_redownload,
            profile=ReportsProfile.DOWNLOAD,
            raw_matches=["redownload"],
            **base_kwargs,
        )
    if _LIST_RE.search(text):
        return ReportsPlan(
            task_type=ReportsTaskType.report_list_recent,
            profile=ReportsProfile.LIST,
            raw_matches=["list"],
            **base_kwargs,
        )

    norm = normalize_reports_text(text)
    if re.search(r"\b(rapports?|reports?|exports?)\b", norm) and len(norm.split()) > 2:
        return ReportsPlan(
            task_type=ReportsTaskType.report_list_recent,
            profile=ReportsProfile.LIST,
            raw_matches=["list_default"],
            **base_kwargs,
        )

    if is_reports_grey_zone(text):
        return ReportsPlan(
            task_type=ReportsTaskType.ambiguous,
            needs_router=True,
            raw_matches=["grey_zone"],
        )

    return ReportsPlan(
        task_type=ReportsTaskType.ambiguous,
        needs_router=True,
        raw_matches=["vague"],
    )
