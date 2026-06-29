"""Snapshot Centre de rapports — parité stricte UI / API / agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.report_run import ReportRun
from app.services.admin_client.reports.reports_types import ReportsPlan, ReportsToolError
from app.services.reports_service import (
    is_run_completed_status,
    list_recent_runs,
    list_reports,
    resolve_run_path,
    run_to_read_dict,
)


def get_reports_center_snapshot(
    db: Session,
    *,
    fmt: str | None = None,
    search: str | None = None,
    slug: str | None = None,
    limit: int = 15,
) -> dict[str, Any]:
    """Miroir GET /api/reports + GET /api/reports/runs/recent."""
    listing = list_reports(db, fmt=fmt, search=search, page_size=min(max(limit, 1), 30))
    recent_reads = list_recent_runs(db, limit=30)

    if fmt:
        fmt_l = fmt.lower()
        recent_reads = [r for r in recent_reads if str(r.format or "").lower() == fmt_l]
    if slug:
        recent_reads = [r for r in recent_reads if r.slug == slug]
    if search:
        needle = search.lower()
        recent_reads = [
            r
            for r in recent_reads
            if needle in (r.name or "").lower()
            or needle in (r.slug or "").lower()
            or needle in (r.category or "").lower()
        ]
    recent_reads = recent_reads[: min(max(limit, 1), 30)]

    recent_runs: list[dict[str, Any]] = []
    file_available: dict[int, bool] = {}

    for read in recent_reads:
        row = read.model_dump(mode="json")
        row["download_url"] = f"/api/reports/runs/{read.id}/download"
        recent_runs.append(row)
        run_obj = db.get(ReportRun, read.id)
        file_available[read.id] = bool(run_obj and resolve_run_path(run_obj) is not None)

    catalog = [item.model_dump(mode="json") for item in listing.items]
    if slug:
        catalog = [c for c in catalog if c.get("slug") == slug]
    if search:
        needle = search.lower()
        catalog = [
            c
            for c in catalog
            if needle in (c.get("name") or "").lower()
            or needle in (c.get("description") or "").lower()
            or needle in (c.get("slug") or "").lower()
        ]

    return {
        "catalog": catalog,
        "recent_runs": recent_runs,
        "file_available": file_available,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {"fmt": fmt, "search": search, "slug": slug},
    }


def _load_run_dict(
    db: Session,
    run_id: int,
    *,
    require_file: bool,
    file_available: dict[int, bool],
) -> dict[str, Any]:
    run_obj = db.get(ReportRun, run_id)
    if run_obj is None:
        raise ReportsToolError("run_not_found")
    if not is_run_completed_status(run_obj.status):
        raise ReportsToolError("run_not_completed")
    if require_file:
        if not file_available.get(run_id):
            raise ReportsToolError("file_missing")
        path = resolve_run_path(run_obj)
        if path is None:
            raise ReportsToolError("file_missing")
        return run_to_read_dict(db, run_obj, resolved_path=path)
    return run_to_read_dict(db, run_obj)


def resolve_target_run(
    db: Session,
    plan: ReportsPlan,
    snapshot: dict[str, Any],
    *,
    require_file: bool = True,
) -> dict[str, Any]:
    """Résolution run — ordre identique au raisonnement Reports Center UI."""
    catalog = snapshot.get("catalog") or []
    recent_runs = snapshot.get("recent_runs") or []
    file_available = snapshot.get("file_available") or {}

    if plan.run_id:
        return _load_run_dict(
            db, plan.run_id, require_file=require_file, file_available=file_available
        )

    if plan.slug_hint:
        for item in catalog:
            if item.get("slug") == plan.slug_hint and item.get("last_run_id"):
                return _load_run_dict(
                    db,
                    int(item["last_run_id"]),
                    require_file=require_file,
                    file_available=file_available,
                )

    candidates = list(recent_runs)
    if plan.format_filter:
        fmt = plan.format_filter.lower()
        filtered = [r for r in candidates if str(r.get("format", "")).lower() == fmt]
        if filtered:
            candidates = filtered
        elif require_file:
            raise ReportsToolError(f"format_not_found:{fmt}")

    for row in candidates:
        rid = int(row["id"])
        if require_file:
            if file_available.get(rid):
                return _load_run_dict(
                    db, rid, require_file=True, file_available=file_available
                )
        else:
            return _load_run_dict(
                db, rid, require_file=False, file_available=file_available
            )

    if require_file:
        for row in recent_runs:
            rid = int(row["id"])
            if file_available.get(rid):
                return _load_run_dict(
                    db, rid, require_file=True, file_available=file_available
                )
        raise ReportsToolError("file_missing")

    if recent_runs:
        return _load_run_dict(
            db,
            int(recent_runs[0]["id"]),
            require_file=False,
            file_available=file_available,
        )
    raise ReportsToolError("run_not_found")
