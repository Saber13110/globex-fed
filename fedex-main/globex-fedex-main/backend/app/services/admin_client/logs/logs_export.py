"""Export Excel / PDF des journaux admin — détection format et génération fichier."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.services.admin_client.logs.logs_followup import has_logs_list_data, is_logs_history_context
from app.services.admin_client.logs.logs_types import LogsPlan, LogsProfile, LogsTaskType
from app.services.admin_logs_export_service import (
    generate_activity_logs_excel,
    generate_activity_logs_pdf,
    parse_log_period_hours,
)
from app.services.ai_assistant.export_dataset_cache import store_client_excel_blob, store_pdf_blob
from app.services.client_phase3.export_intent import (
    has_explicit_excel_format,
    has_explicit_pdf_format,
)
from app.services.client_phase3.pdf_text import append_pdf_ready_note
from app.services.copilot_export_service import build_export_download_spec

LogsExportFormat = Literal["pdf", "xlsx"]

_LOGS_EXPORT_UTTERANCE_RE = re.compile(
    r"\b("
    r"(excel|xlsx|pdf|fichier|export|t[eé]l[eé]charg).{0,55}(logs?|journaux?)|"
    r"(logs?|journaux?).{0,55}(excel|xlsx|pdf|fichier|export|t[eé]l[eé]charg)"
    r")\b",
    re.I,
)

_GENERIC_EXPORT_RE = re.compile(
    r"\b(fichier|export|t[eé]l[eé]charg|document|forme)\b",
    re.I,
)


def export_format_clarify_question(lang: str) -> str:
    if lang == "en":
        return "Do you want the activity logs as **Excel** (.xlsx) or **PDF**?"
    return "Souhaitez-vous les journaux d'activité en **Excel** (.xlsx) ou en **PDF** ?"


def resolve_logs_export_format(message: str) -> LogsExportFormat | None:
    """Retourne pdf/xlsx si le format est explicite, sinon None."""
    text = (message or "").strip()
    if not text:
        return None
    wants_excel = has_explicit_excel_format(text)
    wants_pdf = has_explicit_pdf_format(text)
    if wants_excel and not wants_pdf:
        return "xlsx"
    if wants_pdf and not wants_excel:
        return "pdf"
    return None


def has_conflicting_export_formats(message: str) -> bool:
    text = (message or "").strip()
    return has_explicit_excel_format(text) and has_explicit_pdf_format(text)


def is_logs_direct_export_message(message: str) -> bool:
    """Demande logs + export en une seule phrase (sans historique obligatoire)."""
    text = (message or "").strip()
    if not text or not _LOGS_EXPORT_UTTERANCE_RE.search(text):
        return False
    if resolve_logs_export_format(text):
        return True
    return bool(_GENERIC_EXPORT_RE.search(text))


def is_logs_excel_followup(message: str, *, history_text: str = "") -> bool:
    """Excel demandé après une liste/résumé logs."""
    from app.services.client_phase3.excel_postprocess import wants_excel_format

    text = (message or "").strip()
    if not text:
        return False
    hist = history_text or ""
    if not (has_logs_list_data(hist) or is_logs_history_context(hist)):
        return False
    from app.services.admin_client.security.security_followup import is_security_history_context
    from app.services.admin_client.security.security_patterns import is_security_report_message

    if is_security_history_context(hist) or is_security_report_message(text):
        return False
    if has_conflicting_export_formats(text):
        return False
    if resolve_logs_export_format(text) == "xlsx":
        return True
    if wants_excel_format(text):
        return True
    return bool(
        re.search(r"\b(excel|xlsx|tableur)\b", text, re.I) and len(text) <= 120
    )


def is_logs_pdf_followup(message: str, *, history_text: str = "") -> bool:
    """PDF demandé après une liste/résumé logs — pas si Excel est demandé."""
    from app.services.client_phase3.excel_postprocess import wants_excel_format
    from app.services.client_phase3.pdf_postprocess import is_pdf_only_followup, wants_pdf_format

    text = (message or "").strip()
    if not text:
        return False
    hist = history_text or ""
    if not (has_logs_list_data(hist) or is_logs_history_context(hist)):
        return False
    from app.services.admin_client.security.security_followup import is_security_history_context
    from app.services.admin_client.security.security_patterns import is_security_report_message

    if is_security_history_context(hist) or is_security_report_message(text):
        return False
    if wants_excel_format(text) or resolve_logs_export_format(text) == "xlsx":
        return False
    if has_conflicting_export_formats(text):
        return False
    if resolve_logs_export_format(text) == "pdf":
        return True
    if wants_pdf_format(text) or is_pdf_only_followup(text):
        return True
    return bool(
        re.search(
            r"\b(pdf|t[eé]l[eé]charg|export|forme|document)\b",
            text,
            re.I,
        )
        and len(text) <= 120
        and not has_explicit_excel_format(text)
    )


def infer_list_plan_from_history(
    history_text: str,
    *,
    want_pdf: bool = False,
    want_excel: bool = False,
    message: str = "",
) -> LogsPlan:
    """Rejoue la dernière liste visible avec export demandé."""
    combined = f"{history_text or ''}\n{message or ''}"
    hours = parse_log_period_hours(combined, default=24)
    since_today = bool(re.search(r"\baujourd.?hui\b|du\s+jour|dernier\s+jour", combined, re.I))
    level = None
    m = re.search(r"niveau=(\w+)", history_text or "", re.I)
    if m:
        level = m.group(1).upper()
    raw = "excel_followup" if want_excel else "pdf_followup"
    return LogsPlan(
        task_type=LogsTaskType.log_list,
        profile=LogsProfile.LIST,
        period_hours=None if since_today else hours,
        since_today=since_today,
        level_filter=level,
        want_pdf=want_pdf,
        want_excel=want_excel,
        limit=30,
        raw_matches=[raw],
    )


def infer_export_plan_from_message(message: str, *, lang: str = "fr") -> LogsPlan | None:
    """Plan liste + export pour une demande directe (ex. excel logs 24h)."""
    text = (message or "").strip()
    if not is_logs_direct_export_message(text):
        return None
    if has_conflicting_export_formats(text):
        return LogsPlan(
            task_type=LogsTaskType.log_list,
            profile=LogsProfile.CLARIFY,
            needs_clarification=True,
            clarification_question=export_format_clarify_question(lang),
            raw_matches=["export_format_conflict"],
        )
    fmt = resolve_logs_export_format(text)
    if fmt is None and _GENERIC_EXPORT_RE.search(text):
        return LogsPlan(
            task_type=LogsTaskType.log_list,
            profile=LogsProfile.CLARIFY,
            needs_clarification=True,
            clarification_question=export_format_clarify_question(lang),
            raw_matches=["export_format_missing"],
        )
    hours = parse_log_period_hours(text, default=24)
    since_today = bool(re.search(r"\b(aujourd.?hui|du\s+jour|dernier\s+jour)\b", text, re.I))
    plan = LogsPlan(
        task_type=LogsTaskType.log_list,
        profile=LogsProfile.LIST,
        period_hours=None if since_today else hours,
        since_today=since_today,
        limit=500,
        raw_matches=["direct_export"],
    )
    if fmt == "xlsx":
        plan.want_excel = True
    elif fmt == "pdf":
        plan.want_pdf = True
    return plan


def _rows_from_processed(processed: dict[str, Any]) -> list[Any]:
    from app.models.activity_log import ActivityLog

    logs_raw = processed.get("logs") or []
    rows = []
    for item in logs_raw:
        row = ActivityLog(
            id=item.get("id") or 0,
            level=str(item.get("level") or "INFO"),
            category=str(item.get("category") or "system"),
            action=str(item.get("action") or ""),
            message=str(item.get("message") or ""),
        )
        row.created_at = item.get("created_at")
        rows.append(row)
    return rows


def build_logs_pdf_export(
    admin_id: int,
    session_id: int,
    *,
    processed: dict[str, Any],
    hours: int = 24,
    lang: str = "fr",
) -> tuple[str, dict[str, Any] | None]:
    rows = _rows_from_processed(processed)
    if not rows:
        return (
            "Aucun log à exporter en PDF."
            if lang == "fr"
            else "No logs to export as PDF.",
            None,
        )

    pdf_bytes, filename = generate_activity_logs_pdf(rows, hours=hours)
    token = store_pdf_blob(
        admin_id=admin_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        module="logs",
        meta={"hours": hours, "count": len(rows)},
    )
    export_download = build_export_download_spec(
        preset="admin_logs",
        filename=filename,
        fmt="pdf",
        export_token=token,
        module="logs",
    )
    note = (
        "Votre PDF journaux est prêt — utilisez le lien de téléchargement ci-dessous."
        if lang == "fr"
        else "Your activity logs PDF is ready — use the download link below."
    )
    return append_pdf_ready_note(note), export_download


def build_logs_excel_export(
    admin_id: int,
    session_id: int,
    *,
    processed: dict[str, Any],
    hours: int = 24,
    lang: str = "fr",
) -> tuple[str, dict[str, Any] | None]:
    rows = _rows_from_processed(processed)
    if not rows:
        return (
            "Aucun log à exporter en Excel."
            if lang == "fr"
            else "No logs to export as Excel.",
            None,
        )

    xlsx_bytes, filename = generate_activity_logs_excel(rows, hours=hours)
    token = store_client_excel_blob(
        user_id=admin_id,
        xlsx_bytes=xlsx_bytes,
        filename=filename,
        module="logs",
        meta={"hours": hours, "count": len(rows), "session_id": session_id},
    )
    export_download = build_export_download_spec(
        preset="admin_logs",
        filename=filename,
        fmt="xlsx",
        export_token=token,
        module="logs",
    )
    note = (
        "Votre fichier Excel des journaux est prêt — utilisez le lien de téléchargement ci-dessous."
        if lang == "fr"
        else "Your activity logs Excel file is ready — use the download link below."
    )
    return note, export_download
