import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.platform_notification import PlatformNotification
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.notifications import (
    AiReportNotificationResponse,
    CreateRuleRequest,
    NotificationItem,
    NotificationListResponse,
    NotificationOverview,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    TestAlertRequest,
    WebhookImportResponse,
)
from app.services.notifications_service import (
    archive_notification,
    build_overview,
    build_stats,
    create_rule,
    create_test_alert,
    delete_notification,
    export_notifications,
    generate_ai_report,
    get_preferences,
    import_fedex_webhooks,
    list_notifications,
    mark_all_read,
    mark_read,
    save_preferences,
    unread_count,
)

router = APIRouter(prefix="/api/admin/notifications", tags=["admin-notifications"])


@router.get("", response_model=NotificationListResponse)
def get_notifications(
    tab: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("newest"),
    status: str = Query("all"),
    priority: str = Query("all"),
    channel: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=50),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    return list_notifications(
        db,
        tab=tab,
        search=search,
        sort=sort,
        status=status,
        priority=priority,
        channel=channel,
        page=page,
        page_size=page_size,
    )


@router.get("/stats")
def get_stats(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return build_stats(db)


@router.get("/overview", response_model=NotificationOverview)
def get_overview(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationOverview:
    return build_overview(db)


@router.get("/unread-count")
def get_unread_count(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    return {"count": unread_count(db)}


@router.patch("/{notif_id}/read", response_model=NotificationItem)
def patch_read(
    notif_id: int,
    read: bool = Query(True),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationItem:
    item = mark_read(db, notif_id, read=read)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    return item


@router.patch("/read-all")
def patch_read_all(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    count = mark_all_read(db)
    return {"updated": count}


@router.delete("/{notif_id}")
def remove_notification(
    notif_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if not delete_notification(db, notif_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    return {"ok": True}


@router.post("/{notif_id}/archive", response_model=NotificationItem)
def post_archive(
    notif_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationItem:
    item = archive_notification(db, notif_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    return item


@router.get("/preferences", response_model=NotificationPreferences)
def get_notification_preferences(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationPreferences:
    return get_preferences(db, admin.id)


@router.patch("/preferences", response_model=NotificationPreferences)
def patch_notification_preferences(
    payload: NotificationPreferencesUpdate,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationPreferences:
    patch = payload.model_dump(exclude_unset=True)
    return save_preferences(db, admin.id, patch)


@router.get("/export")
def export_history(
    format: str = Query("csv", alias="format"),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Response:
    fmt = "xlsx" if format.lower() in ("xlsx", "excel") else "csv"
    content, media, filename = export_notifications(db, fmt)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/test-alert", response_model=NotificationItem)
def post_test_alert(
    payload: TestAlertRequest,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationItem:
    return create_test_alert(db, payload)


@router.post("/rules", response_model=NotificationItem)
def post_create_rule(
    payload: CreateRuleRequest,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationItem:
    return create_rule(db, payload)


@router.post("/ai-report", response_model=AiReportNotificationResponse)
def post_ai_report(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AiReportNotificationResponse:
    return generate_ai_report(db)


@router.get("/stream")
async def notification_stream(
    request: Request,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """SSE — mise à jour du compteur non lu en temps réel."""

    async def event_generator():
        last_count = -1
        while True:
            if await request.is_disconnected():
                break
            count = unread_count(db)
            if count != last_count:
                payload = json.dumps({"unread_count": count, "event": "count_updated"})
                yield f"data: {payload}\n\n"
                last_count = count
            else:
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# FedEx webhooks — monté aussi sous /api/fedex/webhooks/import via alias
webhooks_router = APIRouter(prefix="/api/fedex/webhooks", tags=["fedex-webhooks"])


@webhooks_router.post("/import", response_model=WebhookImportResponse)
def post_import_webhooks(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> WebhookImportResponse:
    return import_fedex_webhooks(db)
