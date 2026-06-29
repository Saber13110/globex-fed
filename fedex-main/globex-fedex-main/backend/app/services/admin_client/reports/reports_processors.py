"""Traitement déterministe des données reports — pas de LLM."""

from __future__ import annotations

import re
from typing import Any

from app.services.admin_client.reports.reports_types import ReportsPlan, ReportsTaskType
from app.services.reports_service import is_run_completed_status

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def validate_report_data(run: dict[str, Any] | None, preview: dict[str, Any] | None = None) -> dict[str, Any]:
    if not run:
        return {"valid": False, "missing_file": True, "status_ok": False, "message": "run_missing"}
    status_ok = is_run_completed_status(str(run.get("status") or ""))
    missing_file = not bool(run.get("file_path") or run.get("download_url"))
    valid = status_ok and not missing_file
    return {
        "valid": valid,
        "missing_file": missing_file,
        "status_ok": status_ok,
        "message": "" if valid else "report_invalid_or_incomplete",
    }


def summarize_report_preview(preview: dict[str, Any] | None) -> dict[str, Any]:
    if not preview:
        return {"columns": [], "sample_rows": [], "total_rows": 0}
    rows = preview.get("rows") or []
    return {
        "columns": preview.get("columns") or [],
        "sample_rows": rows[:10],
        "total_rows": int(preview.get("total_rows") or 0),
    }


def resolve_recipients(
    message: str,
    users: list[dict[str, Any]],
    *,
    explicit_query: str = "",
) -> list[dict[str, Any]]:
    emails = _EMAIL_RE.findall(message or "")
    if explicit_query and "@" in explicit_query:
        emails.append(explicit_query.strip())
    emails = list(dict.fromkeys(e.lower() for e in emails))

    resolved: list[dict[str, Any]] = []
    for email in emails:
        match = next((u for u in users if str(u.get("email", "")).lower() == email), None)
        if match and str(match.get("status") or "") == "active":
            resolved.append(match)
        elif match:
            resolved.append({**match, "inactive": True})

    if not resolved and users:
        active = [u for u in users if str(u.get("status") or "") == "active" and u.get("email")]
        if len(active) == 1:
            resolved.append(active[0])
    return resolved


def process_report_data(
    *,
    plan: ReportsPlan,
    runs: list[dict[str, Any]],
    run: dict[str, Any] | None,
    preview: dict[str, Any] | None,
    recipients: list[dict[str, Any]],
) -> dict[str, Any]:
    validation = validate_report_data(run, preview)
    if plan.task_type == ReportsTaskType.report_share:
        validation = {**validation, "valid": bool(run), "missing_file": False}
    preview_summary = summarize_report_preview(preview) if preview else None
    tools_run = ["validate_report_data"]
    if preview_summary:
        tools_run.append("summarize_report_preview")
    if plan.task_type == ReportsTaskType.report_share:
        tools_run.append("resolve_recipients")
    return {
        "runs": runs,
        "run": run,
        "preview": preview,
        "preview_summary": preview_summary,
        "validation": validation,
        "recipients": recipients,
        "tools_run": tools_run,
    }
