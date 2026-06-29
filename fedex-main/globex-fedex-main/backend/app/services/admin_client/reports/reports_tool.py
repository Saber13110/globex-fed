"""Façade outils reports admin — délégation stricte à reports_service / snapshot."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.reports.reports_center_snapshot import (
    get_reports_center_snapshot,
    resolve_target_run,
)
from app.services.admin_client.reports.reports_types import ReportsPlan, ReportsToolError
from app.services.reports_service import (
    get_run_file,
    preview_run,
    run_to_read_dict,
    share_run_by_email,
    share_run_preview,
)

# Réexport pour compatibilité imports existants
__all__ = [
    "ReportsToolError",
    "fetch_reports_center",
    "list_recent_report_runs",
    "get_report_run",
    "get_report_run_meta",
    "get_run_download",
    "preview_report",
    "resolve_target_run",
    "search_users_for_reports",
    "share_report_email",
    "share_run_preview_tool",
    "run_file_is_available",
]


def fetch_reports_center(
    db: Session,
    *,
    fmt: str | None = None,
    search: str | None = None,
    slug: str | None = None,
    limit: int = 15,
) -> dict[str, Any]:
    return get_reports_center_snapshot(db, fmt=fmt, search=search, slug=slug, limit=limit)


def list_recent_report_runs(
    db: Session,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    snapshot = fetch_reports_center(db, limit=limit)
    return list(snapshot.get("recent_runs") or [])


def get_report_run_meta(db: Session, run_id: int) -> dict[str, Any]:
    from app.models.report_run import ReportRun

    run = db.get(ReportRun, run_id)
    if run is None:
        raise ReportsToolError("run_not_found")
    return run_to_read_dict(db, run)


def get_run_download(db: Session, run_id: int) -> dict[str, Any]:
    try:
        run, path = get_run_file(db, run_id)
    except FileNotFoundError as exc:
        code = str(getattr(exc, "args", ["file_missing"])[0] or "file_missing")
        raise ReportsToolError(code) from exc
    return run_to_read_dict(db, run, resolved_path=path)


def get_report_run(db: Session, run_id: int) -> dict[str, Any]:
    return get_run_download(db, run_id)


def preview_report(db: Session, run_id: int) -> dict[str, Any]:
    try:
        preview = preview_run(db, run_id)
        run_data = get_run_download(db, run_id)
    except FileNotFoundError as exc:
        raise ReportsToolError(str(getattr(exc, "args", ["preview_failed"])[0] or "preview_failed")) from exc
    return {
        "run": run_data,
        "columns": preview.columns,
        "rows": preview.rows,
        "total_rows": preview.total_rows,
    }


def share_run_preview_tool(
    db: Session,
    run_id: int,
    recipient_emails: list[str] | None = None,
) -> dict[str, Any]:
    try:
        return share_run_preview(db, run_id, recipient_emails)
    except FileNotFoundError as exc:
        raise ReportsToolError("run_not_found") from exc


def search_users_for_reports(db: Session, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    stmt = select(User).order_by(User.created_at.desc()).limit(min(limit, 20))
    if q.isdigit():
        stmt = stmt.where(or_(User.id == int(q), User.email.ilike(f"%{q}%")))
    else:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    rows = list(db.scalars(stmt).all())
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name or "",
            "role": u.role,
            "status": u.status,
        }
        for u in rows
    ]


def share_report_email(
    db: Session,
    *,
    run_id: int,
    recipient_emails: list[str],
    admin_id: int,
) -> dict[str, Any]:
    try:
        return share_run_by_email(db, run_id=run_id, recipient_emails=recipient_emails, admin_id=admin_id)
    except FileNotFoundError as exc:
        raise ReportsToolError("share_failed") from exc


def run_file_is_available(db: Session, run_id: int) -> bool:
    snapshot = fetch_reports_center(db, limit=30)
    return bool((snapshot.get("file_available") or {}).get(run_id))
