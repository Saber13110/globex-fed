from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.tracking import TrackingResponse
from app.schemas.visibility import VisibilityEventsResponse
from app.services import fedex_service
from app.services.activity_log_service import client_ip, mask_sensitive_text, write_log
from app.services.shipment_cache_service import upsert_shipment_cache
from app.services.fedex_sandbox_whitelist import FedExSandboxWhitelistError, SANDBOX_WHITELIST_MESSAGE
from app.services.fedex_visibility_service import (
    get_pod_record,
    list_visibility_events,
    sync_visibility_from_tracking,
    upsert_pod_from_shipment,
)
from app.services.proof_of_delivery_service import (
    get_pod_info_for_tracking,
    get_proof_of_delivery_pdf,
    is_likely_delivered,
    is_pod_available,
)
from app.services.quota_service import enforce_daily_quota
from app.services.tracking_presenter import build_tracking_response
from app.services.user_notification_service import maybe_notify_shipment_events

router = APIRouter(prefix="/tracking", tags=["tracking"])


def _whitelist_http_detail(tracking_number: str) -> dict[str, str]:
    return {
        "code": FedExSandboxWhitelistError.code,
        "message": SANDBOX_WHITELIST_MESSAGE,
        "tracking_number": tracking_number.strip().upper(),
    }


def _pod_available_for(data: dict[str, Any]) -> bool:
    return is_pod_available(data)


def _enrich_tracking(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if settings.fedex_visibility_sync_on_track:
        sync_visibility_from_tracking(db, data, source="tracking_sync", commit=False)
        if is_likely_delivered(data.get("status"), data.get("events")):
            upsert_pod_from_shipment(db, data, commit=False)
    visibility_events = list_visibility_events(db, data["tracking_number"])
    pod_info = get_pod_info_for_tracking(data, get_pod_record(db, data["tracking_number"]))
    pod_available = _pod_available_for(data)
    return {
        "visibility_events": visibility_events,
        "pod_info": pod_info,
        "pod_available": pod_available,
    }


@router.get("/{tracking_number}/proof-of-delivery")
def download_proof_of_delivery(
    tracking_number: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    enforce_daily_quota(db, user, kind="trackings")
    try:
        shipment = fedex_service.get_shipment(tracking_number)
    except FedExSandboxWhitelistError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_whitelist_http_detail(exc.tracking_number),
        ) from exc
    except fedex_service.TrackingLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not _pod_available_for(shipment):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La preuve de livraison est disponible une fois le colis livré.",
        )

    extras = _enrich_tracking(db, shipment)
    pod_info = extras.get("pod_info")

    try:
        pdf_bytes = get_proof_of_delivery_pdf(
            shipment["tracking_number"],
            pod_info=pod_info,
            shipment_data=shipment,
        )
    except fedex_service.TrackingLookupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    masked = mask_sensitive_text(shipment["tracking_number"], max_len=40)
    write_log(
        db,
        action="tracking.proof_of_delivery",
        message=f"Preuve de livraison téléchargée : {masked}",
        category="system",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"tracking_number_masked": masked},
        commit=True,
    )

    filename = f"preuve-livraison-{shipment['tracking_number']}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{tracking_number}/visibility-events", response_model=VisibilityEventsResponse)
def get_visibility_events(
    tracking_number: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VisibilityEventsResponse:
    _ = user
    tn = tracking_number.strip().upper()
    events = list_visibility_events(db, tn)
    return VisibilityEventsResponse(tracking_number=tn, events=events, count=len(events))


@router.get("/{tracking_number}", response_model=TrackingResponse)
def get_tracking(
    tracking_number: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrackingResponse:
    enforce_daily_quota(db, user, kind="trackings")
    try:
        data = fedex_service.get_shipment(tracking_number)
    except FedExSandboxWhitelistError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_whitelist_http_detail(exc.tracking_number),
        ) from exc
    except fedex_service.TrackingLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    extras = _enrich_tracking(db, data)

    maybe_notify_shipment_events(
        db,
        user_id=user.id,
        data=data,
        pod_available=extras["pod_available"],
    )
    upsert_shipment_cache(db, data)
    write_log(
        db,
        action="tracking.lookup",
        message=f"Suivi FedEx : {mask_sensitive_text(tracking_number, max_len=40)}",
        category="system",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"status": data.get("status"), "visibility_events": len(extras["visibility_events"])},
        commit=False,
    )
    db.commit()

    return build_tracking_response(data, extras)
