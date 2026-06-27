"""Centre de rapports admin — KPIs, graphiques, génération et exports."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.report_run import ReportRun
from app.models.report_schedule import ReportSchedule
from app.models.tracking_request import TrackingRequest
from app.models.user import User
from app.schemas.reports import (
    ChartPoint,
    ReportCatalogItem,
    ReportGenerateResponse,
    ReportKpiItem,
    ReportListResponse,
    ReportPreviewResponse,
    ReportRunRead,
    ReportScheduleCreate,
    ReportScheduleRead,
    ReportsChartsResponse,
    ReportsKpisResponse,
)

REPORT_CATALOG: list[dict[str, str]] = [
    {
        "slug": "tracking-history",
        "name": "Tracking History",
        "description": "Complete shipment tracking history export",
        "category": "shipments",
        "default_format": "xlsx",
    },
    {
        "slug": "delivery-performance",
        "name": "Delivery Performance",
        "description": "On-time delivery and SLA performance metrics",
        "category": "performance",
        "default_format": "xlsx",
    },
    {
        "slug": "exception-report",
        "name": "Exception Report",
        "description": "Shipment exceptions and operational incidents",
        "category": "exceptions",
        "default_format": "pdf",
    },
    {
        "slug": "financial-summary",
        "name": "Financial Summary",
        "description": "Operational cost and volume summary",
        "category": "finance",
        "default_format": "xlsx",
    },
    {
        "slug": "customer-activity",
        "name": "Customer Activity",
        "description": "User engagement and tracking activity",
        "category": "shipments",
        "default_format": "csv",
    },
    {
        "slug": "custom-report",
        "name": "Custom Report",
        "description": "Build a tailored export from platform data",
        "category": "custom",
        "default_format": "pdf",
    },
]

REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "reports"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dates(date_from: str | None, date_to: str | None) -> tuple[datetime, datetime]:
    end = _now()
    start = end - timedelta(days=30)
    if date_to:
        try:
            end = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if date_from:
        try:
            start = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return start, end


def _period_label(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}"


def _status_bucket(status: str | None) -> str:
    s = (status or "").lower()
    if any(x in s for x in ("deliver", "livré", "livre")):
        return "delivered"
    if any(x in s for x in ("exception", "incident", "fail", "échec")):
        return "exception"
    if any(x in s for x in ("delay", "retard", "late")):
        return "delayed"
    if any(x in s for x in ("return", "retour")):
        return "return"
    if any(x in s for x in ("transit", "route", "ship")):
        return "in_transit"
    return "other"


def _tracking_query(db: Session, start: datetime, end: datetime):
    return (
        select(TrackingRequest)
        .where(TrackingRequest.created_at >= start, TrackingRequest.created_at <= end)
        .order_by(TrackingRequest.created_at.desc())
    )


def _fetch_rows(db: Session, start: datetime, end: datetime, slug: str, limit: int = 5000) -> list[TrackingRequest]:
    stmt = _tracking_query(db, start, end).limit(limit)
    if slug == "exception-report":
        stmt = stmt.where(
            or_(
                TrackingRequest.status.ilike("%exception%"),
                TrackingRequest.status.ilike("%incident%"),
                TrackingRequest.status.ilike("%fail%"),
            )
        )
    return list(db.scalars(stmt).all())


def _trend_percent(current: float, previous: float) -> tuple[float, bool]:
    if previous <= 0:
        return (12.5 if current > 0 else 0.0, True)
    pct = ((current - previous) / previous) * 100
    return (round(pct, 1), pct >= 0)


def _sparkline(db: Session, days: int = 7) -> list[float]:
    out: list[float] = []
    for i in range(days - 1, -1, -1):
        day = _now().date() - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        n = int(
            db.scalar(
                select(func.count())
                .select_from(TrackingRequest)
                .where(TrackingRequest.created_at >= day_start, TrackingRequest.created_at < day_end)
            )
            or 0
        )
        out.append(float(n))
    return out or [0.0]


def build_kpis(db: Session, date_from: str | None, date_to: str | None) -> ReportsKpisResponse:
    start, end = _parse_dates(date_from, date_to)
    prev_span = end - start
    prev_start = start - prev_span
    prev_end = start

    def metrics(s: datetime, e: datetime) -> dict[str, float]:
        rows = list(db.scalars(_tracking_query(db, s, e).limit(10000)).all())
        total = len(rows)
        delivered = sum(1 for r in rows if _status_bucket(r.status) == "delivered")
        delayed = sum(1 for r in rows if _status_bucket(r.status) == "delayed")
        exceptions = sum(1 for r in rows if _status_bucket(r.status) == "exception")
        returns = sum(1 for r in rows if _status_bucket(r.status) == "return")
        rate = (returns / total * 100) if total else 0.0
        return {
            "shipments": float(total),
            "delivered": float(delivered),
            "delayed": float(delayed),
            "exceptions": float(exceptions),
            "return_rate": round(rate, 1),
        }

    cur = metrics(start, end)
    prev = metrics(prev_start, prev_end)
    spark = _sparkline(db)

    def kpi(key: str, label: str, value: float, fmt: str) -> ReportKpiItem:
        t, up = _trend_percent(value, prev.get(key.replace("_rate", "").replace("return", "exceptions"), 0))
        if key == "return_rate":
            t, up = _trend_percent(value, prev["return_rate"])
        return ReportKpiItem(
            key=key,
            label=label,
            value=value,
            display_value=fmt.format(value) if "rate" in key else f"{int(value):,}".replace(",", " "),
            trend_percent=t,
            trend_up=up,
            sparkline=spark,
        )

    return ReportsKpisResponse(
        items=[
            kpi("shipments", "Shipments", cur["shipments"], "{:,.0f}"),
            kpi("delivered", "Delivered", cur["delivered"], "{:,.0f}"),
            kpi("delayed", "Delayed", cur["delayed"], "{:,.0f}"),
            kpi("exceptions", "Exceptions", cur["exceptions"], "{:,.0f}"),
            kpi("return_rate", "Return Rate", cur["return_rate"], "{:.1f}%"),
        ],
        period_from=start,
        period_to=end,
    )


def build_charts(db: Session, date_from: str | None, date_to: str | None) -> ReportsChartsResponse:
    start, end = _parse_dates(date_from, date_to)
    trend: list[ChartPoint] = []
    for i in range(6, -1, -1):
        day = (_now().date() - timedelta(days=i))
        ds = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        de = ds + timedelta(days=1)
        n = int(
            db.scalar(
                select(func.count())
                .select_from(TrackingRequest)
                .where(TrackingRequest.created_at >= ds, TrackingRequest.created_at < de)
            )
            or 0
        )
        trend.append(ChartPoint(name=day.strftime("%d/%m"), value=float(n)))

    rows = list(db.scalars(_tracking_query(db, start, end).limit(5000)).all())
    perf: dict[str, int] = {}
    delay_pie: dict[str, int] = {"On Time": 0, "Delayed": 0, "Exception": 0}
    countries: dict[str, int] = {}

    for r in rows:
        b = _status_bucket(r.status)
        perf[b] = perf.get(b, 0) + 1
        if b == "delayed":
            delay_pie["Delayed"] += 1
        elif b == "exception":
            delay_pie["Exception"] += 1
        else:
            delay_pie["On Time"] += 1
        loc = (r.current_location or "Unknown").strip()
        country = loc.split(",")[-1].strip() if "," in loc else loc.split()[-1]
        countries[country[:40] or "Unknown"] = countries.get(country[:40] or "Unknown", 0) + 1

    return ReportsChartsResponse(
        shipments_trend=trend,
        delivery_performance=[ChartPoint(name=k.replace("_", " ").title(), value=float(v)) for k, v in perf.items()],
        delayed_shipments=[ChartPoint(name=k, value=float(v)) for k, v in delay_pie.items() if v > 0],
        country_statistics=sorted(
            [ChartPoint(name=k, value=float(v)) for k, v in countries.items()],
            key=lambda x: x.value,
            reverse=True,
        )[:8],
    )


def _catalog_item(db: Session, spec: dict[str, str], start: datetime, end: datetime) -> ReportCatalogItem:
    last = db.scalars(
        select(ReportRun).where(ReportRun.slug == spec["slug"]).order_by(ReportRun.created_at.desc()).limit(1)
    ).first()
    gen_name = None
    if last and last.generated_by_user_id:
        u = db.get(User, last.generated_by_user_id)
        gen_name = u.full_name if u else None
    return ReportCatalogItem(
        slug=spec["slug"],
        name=spec["name"],
        description=spec["description"],
        category=spec["category"],
        default_format=spec["default_format"],
        period=_period_label(start, end),
        last_run_id=last.id if last else None,
        last_status=last.status if last else None,
        last_created_at=last.created_at if last else None,
        generated_by_name=gen_name,
    )


def list_reports(
    db: Session,
    *,
    tab: str = "all",
    category: str | None = None,
    search: str | None = None,
    fmt: str | None = None,
    page: int = 1,
    page_size: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> ReportListResponse:
    start, end = _parse_dates(date_from, date_to)
    catalog = []
    for spec in REPORT_CATALOG:
        if tab != "all" and spec["category"] != tab:
            continue
        if category and category != "all" and spec["category"] != category:
            continue
        if search and search.lower() not in spec["name"].lower() and search.lower() not in spec["description"].lower():
            continue
        catalog.append(_catalog_item(db, spec, start, end))

    run_stmt = select(ReportRun).order_by(ReportRun.created_at.desc())
    if fmt and fmt != "all":
        run_stmt = run_stmt.where(ReportRun.format == fmt)
    total = len(catalog)
    offset = (page - 1) * page_size
    runs = list(db.scalars(run_stmt.offset(0).limit(50)).all())
    return ReportListResponse(
        items=catalog[offset : offset + page_size],
        runs=[_run_to_read(db, r) for r in runs[:12]],
        total=total,
        page=page,
        page_size=page_size,
    )


def _run_to_read(db: Session, run: ReportRun) -> ReportRunRead:
    name = None
    if run.generated_by_user_id:
        u = db.get(User, run.generated_by_user_id)
        name = u.full_name if u else None
    return ReportRunRead(
        id=run.id,
        slug=run.slug,
        name=run.name,
        category=run.category,
        format=run.format,
        period_label=run.period_label,
        status=run.status,
        file_size=run.file_size,
        row_count=run.row_count,
        generated_by_name=name,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def _write_xlsx(rows: list[TrackingRequest], path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    headers = ["ID", "Tracking", "Status", "Location", "Delivery", "Created"]
    ws.append(headers)
    for r in rows:
        ws.append(
            [
                r.id,
                r.tracking_number,
                r.status or "",
                r.current_location or "",
                r.estimated_delivery or "",
                r.created_at.isoformat() if r.created_at else "",
            ]
        )
    wb.save(path)


def _write_csv(rows: list[TrackingRequest], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "tracking_number", "status", "location", "estimated_delivery", "created_at"])
        for r in rows:
            w.writerow(
                [
                    r.id,
                    r.tracking_number,
                    r.status or "",
                    r.current_location or "",
                    r.estimated_delivery or "",
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )


def _write_json(rows: list[TrackingRequest], path: Path) -> None:
    payload = [
        {
            "id": r.id,
            "tracking_number": r.tracking_number,
            "status": r.status,
            "current_location": r.current_location,
            "estimated_delivery": r.estimated_delivery,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_pdf(rows: list[TrackingRequest], path: Path, title: str) -> None:
    try:
        from fpdf import FPDF
    except ImportError:
        _write_json(rows, path.with_suffix(".json"))
        path = path.with_suffix(".json")
        return
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title[:80], ln=True)
    pdf.set_font("Helvetica", size=9)
    for r in rows[:80]:
        line = f"{r.tracking_number} | {r.status or '-'} | {r.current_location or '-'}"
        pdf.multi_cell(0, 6, line[:120])
    pdf.output(str(path))


def generate_report(
    db: Session,
    *,
    slug: str,
    fmt: str,
    admin: User,
    date_from: str | None,
    date_to: str | None,
) -> ReportGenerateResponse:
    spec = next((c for c in REPORT_CATALOG if c["slug"] == slug), REPORT_CATALOG[0])
    start, end = _parse_dates(date_from, date_to)
    period = _period_label(start, end)

    run = ReportRun(
        slug=slug,
        name=spec["name"],
        category=spec["category"],
        format=fmt,
        period_label=period,
        status="running",
        generated_by_user_id=admin.id,
    )
    db.add(run)
    db.flush()

    try:
        rows = _fetch_rows(db, start, end, slug)
        _ensure_reports_dir()
        ext = fmt if fmt != "pdf" else "pdf"
        filename = f"report_{run.id}_{slug}.{ext}"
        path = REPORTS_DIR / filename
        if fmt == "xlsx":
            _write_xlsx(rows, path)
        elif fmt == "csv":
            _write_csv(rows, path)
        elif fmt == "json":
            _write_json(rows, path)
        else:
            _write_pdf(rows, path, spec["name"])
            if not path.exists():
                path = path.with_suffix(".json")
                ext = "json"
                run.format = "json"

        size = path.stat().st_size if path.exists() else 0
        run.status = "completed"
        run.file_path = str(path)
        run.file_size = size
        run.row_count = len(rows)
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
        raise

    return ReportGenerateResponse(
        run=_run_to_read(db, run),
        download_url=f"/api/reports/runs/{run.id}/download",
    )


def get_run_file(db: Session, run_id: int) -> tuple[ReportRun, Path]:
    run = db.get(ReportRun, run_id)
    if run is None or not run.file_path:
        raise FileNotFoundError("run_not_found")
    path = Path(run.file_path)
    if not path.is_file():
        raise FileNotFoundError("file_missing")
    return run, path


def preview_run(db: Session, run_id: int) -> ReportPreviewResponse:
    run, path = get_run_file(db, run_id)
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            cols = list(data[0].keys())
            rows = [[str(row.get(c, "")) for c in cols] for row in data[:20]]
            return ReportPreviewResponse(columns=cols, rows=rows, total_rows=len(data))
    return ReportPreviewResponse(
        columns=["Report", "Rows", "Format"],
        rows=[[run.name, str(run.row_count), run.format]],
        total_rows=run.row_count,
    )


def delete_run(db: Session, run_id: int) -> None:
    run = db.get(ReportRun, run_id)
    if run is None:
        raise FileNotFoundError("run_not_found")
    if run.file_path:
        Path(run.file_path).unlink(missing_ok=True)
    db.delete(run)
    db.commit()


def seed_schedules(db: Session, admin_id: int | None) -> list[ReportScheduleRead]:
    existing = db.scalar(select(func.count()).select_from(ReportSchedule)) or 0
    if existing:
        rows = list(db.scalars(select(ReportSchedule).order_by(ReportSchedule.created_at)).all())
        return [_schedule_read(r) for r in rows]

    defaults = [
        ("Daily Tracking Report", "tracking-history", "daily", "08:00", "admin@globex.ma"),
        ("Weekly Performance Report", "delivery-performance", "weekly", "09:00", "admin@globex.ma"),
        ("Monthly Summary", "financial-summary", "monthly", "07:30", "admin@globex.ma,ops@globex.ma"),
    ]
    out = []
    for name, slug, freq, rt, rec in defaults:
        s = ReportSchedule(
            name=name,
            slug=slug,
            frequency=freq,
            run_time=rt,
            recipients=rec,
            format="xlsx",
            active=True,
            created_by_user_id=admin_id,
        )
        db.add(s)
        out.append(s)
    db.commit()
    return [_schedule_read(r) for r in out]


def create_schedule(db: Session, payload: ReportScheduleCreate, admin_id: int) -> ReportScheduleRead:
    row = ReportSchedule(
        name=payload.name,
        slug=payload.slug,
        frequency=payload.frequency,
        run_time=payload.run_time,
        recipients=payload.recipients,
        format=payload.format,
        active=True,
        created_by_user_id=admin_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _schedule_read(row)


def _schedule_read(row: ReportSchedule) -> ReportScheduleRead:
    return ReportScheduleRead(
        id=row.id,
        name=row.name,
        slug=row.slug,
        frequency=row.frequency,
        run_time=row.run_time,
        recipients=row.recipients,
        format=row.format,
        active=row.active,
        created_at=row.created_at,
    )


def suggest_slug_from_prompt(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ("delay", "retard", "late")):
        return "exception-report"
    if any(w in p for w in ("customer", "client", "user", "activit")):
        return "customer-activity"
    if any(w in p for w in ("financ", "cost", "revenue")):
        return "financial-summary"
    if any(w in p for w in ("performance", "delivery", "sla")):
        return "delivery-performance"
    if any(w in p for w in ("month", "weekly", "summary")):
        return "financial-summary"
    return "tracking-history"


def infer_format_from_prompt(prompt: str, default: str = "xlsx") -> str:
    p = prompt.lower()
    if "csv" in p:
        return "csv"
    if "json" in p:
        return "json"
    if "pdf" in p:
        return "pdf"
    if "excel" in p or "xlsx" in p:
        return "xlsx"
    return default
