from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.reports import (
    ReportAiRequest,
    ReportAiResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportListResponse,
    ReportScheduleCreate,
    ReportScheduleRead,
    ReportShareRequest,
    ReportShareResponse,
    ReportsChartsResponse,
    ReportsKpisResponse,
)
from app.services import llm_service
from app.services.activity_log_service import client_ip, write_log
from app.services.reports_service import (
    REPORT_CATALOG,
    build_charts,
    build_kpis,
    create_schedule,
    delete_run,
    generate_report,
    get_run_file,
    infer_format_from_prompt,
    list_reports,
    preview_run,
    seed_schedules,
    suggest_slug_from_prompt,
)

router = APIRouter(tags=["reports"])
ai_router = APIRouter(tags=["ai"])


@router.get("/kpis", response_model=ReportsKpisResponse)
def reports_kpis(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> ReportsKpisResponse:
    return build_kpis(db, date_from, date_to)


@router.get("/charts", response_model=ReportsChartsResponse)
def reports_charts(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> ReportsChartsResponse:
    return build_charts(db, date_from, date_to)


@router.get("", response_model=ReportListResponse)
def reports_list(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    tab: str = Query(default="all"),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    format: str | None = Query(default=None, alias="format"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> ReportListResponse:
    return list_reports(
        db,
        tab=tab,
        category=category,
        search=search,
        fmt=format,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/generate", response_model=ReportGenerateResponse)
def reports_generate(
    payload: ReportGenerateRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ReportGenerateResponse:
    try:
        result = generate_report(
            db,
            slug=payload.slug,
            fmt=payload.format,
            admin=admin,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    write_log(
        db,
        action="reports.generate",
        message=f"Rapport généré: {payload.slug} ({payload.format})",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return result


@router.get("/runs/recent")
def reports_recent(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = Query(default=8, ge=1, le=30),
):
    from app.services.reports_service import _run_to_read
    from app.models.report_run import ReportRun
    from sqlalchemy import select

    rows = list(db.scalars(select(ReportRun).order_by(ReportRun.created_at.desc()).limit(limit)).all())
    return {"items": [_run_to_read(db, r) for r in rows]}


@router.get("/runs/{run_id}/download")
def reports_download(
    run_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    try:
        run, path = get_run_file(db, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable") from exc
    media = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "json": "application/json",
        "pdf": "application/pdf",
    }
    return FileResponse(
        path,
        media_type=media.get(run.format, "application/octet-stream"),
        filename=path.name,
    )


@router.get("/runs/{run_id}/preview")
def reports_preview(
    run_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    try:
        return preview_run(db, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable") from exc


@router.post("/runs/{run_id}/share", response_model=ReportShareResponse)
def reports_share(
    run_id: int,
    request: Request,
    payload: ReportShareRequest | None = None,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ReportShareResponse:
    from app.services.reports_service import share_run_by_email

    body = payload or ReportShareRequest()
    try:
        run, _ = get_run_file(db, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable") from exc

    recipients = [e.strip() for e in body.recipients.replace(";", ",").split(",") if e.strip()]
    if not body.confirm:
        return ReportShareResponse(
            share_url=f"/api/reports/runs/{run.id}/download",
            message="Confirmez l'envoi par e-mail (confirm=true).",
            pending_confirmation=True,
        )

    if not recipients:
        raise HTTPException(status_code=400, detail="Destinataires requis.")

    result = share_run_by_email(db, run_id=run_id, recipient_emails=recipients, admin_id=admin.id)
    write_log(
        db,
        action="reports.share_email",
        message=f"Partage rapport #{run.id}",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"run_id": run_id, "sent_to": result.get("sent_to")},
        commit=True,
    )
    return ReportShareResponse(
        share_url=f"/api/reports/runs/{run.id}/download",
        message="Rapport partagé par e-mail." if result.get("sent_to") else "Aucun e-mail envoyé.",
        sent_to=list(result.get("sent_to") or []),
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def reports_delete(
    run_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    try:
        delete_run(db, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable") from exc
    write_log(
        db,
        action="reports.delete",
        message=f"Suppression rapport #{run_id}",
        category="admin",
        level="WARNING",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )


@router.get("/schedules", response_model=list[ReportScheduleRead])
def reports_schedules(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[ReportScheduleRead]:
    return seed_schedules(db, admin.id)


@router.post("/schedules", response_model=ReportScheduleRead)
def reports_schedule_create(
    payload: ReportScheduleCreate,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ReportScheduleRead:
    return create_schedule(db, payload, admin.id)


@router.get("/export/excel")
@router.get("/export/xlsx")
def export_excel(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    slug: str = Query(default="tracking-history"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    return _export_redirect(db, admin, request, slug, "xlsx", date_from, date_to)


@router.get("/export/csv")
def export_csv(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    slug: str = Query(default="tracking-history"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    return _export_redirect(db, admin, request, slug, "csv", date_from, date_to)


@router.get("/export/json")
def export_json(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    slug: str = Query(default="tracking-history"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    return _export_redirect(db, admin, request, slug, "json", date_from, date_to)


@router.get("/export/pdf")
def export_pdf(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    slug: str = Query(default="exception-report"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    return _export_redirect(db, admin, request, slug, "pdf", date_from, date_to)


def _export_redirect(db, admin, request, slug, fmt, date_from, date_to):
    try:
        result = generate_report(db, slug=slug, fmt=fmt, admin=admin, date_from=date_from, date_to=date_to)
        run, path = get_run_file(db, result.run.id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    write_log(
        db,
        action=f"reports.export_{fmt}",
        message=f"Export {fmt}: {slug}",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    media = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "json": "application/json",
        "pdf": "application/pdf",
    }
    return FileResponse(path, media_type=media.get(run.format, "application/octet-stream"), filename=path.name)


@ai_router.post("/reports", response_model=ReportAiResponse)
def ai_reports(
    payload: ReportAiRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ReportAiResponse:
    slug = suggest_slug_from_prompt(payload.prompt)
    fmt = infer_format_from_prompt(payload.prompt, "xlsx")
    spec = next((c for c in REPORT_CATALOG if c["slug"] == slug), REPORT_CATALOG[0])
    stats = build_kpis(db, None, None)
    context = (
        f"KPIs: shipments={stats.items[0].display_value}, "
        f"delivered={stats.items[1].display_value}, delayed={stats.items[2].display_value}."
    )
    try:
        llm = llm_service.generate_response(
            f"{context}\n\nDemande rapport admin: {payload.prompt}\n"
            f"Propose un résumé exécutif court et les actions recommandées.",
            ui_language=admin.preferred_language or "fr",
        )
        reply = llm.reply
    except Exception as exc:  # noqa: BLE001
        reply = f"Analyse locale: rapport suggéré « {spec['name']} » ({fmt}). Détail: {exc}"

    run_result = None
    download_url = None
    if any(w in payload.prompt.lower() for w in ("export", "generate", "génér", "create", "créer", "rapport")):
        try:
            gen = generate_report(db, slug=slug, fmt=fmt, admin=admin, date_from=None, date_to=None)
            run_result = gen.run
            download_url = gen.download_url
            reply += f"\n\nRapport généré: {spec['name']} ({fmt.upper()})."
        except Exception as exc:  # noqa: BLE001
            reply += f"\n\nGénération automatique échouée: {exc}"

    write_log(
        db,
        action="reports.ai",
        message=f"IA rapport: {payload.prompt[:100]}",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return ReportAiResponse(
        reply=reply,
        suggested_slug=slug,
        run=run_result,
        download_url=download_url,
    )
