"""Endpoints FedEx Advanced Integrated Visibility (webhook + simulateur)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user, require_role
from app.schemas.visibility import WebhookIngestResponse
from app.services import fedex_service
from app.services.activity_log_service import client_ip, write_log
from app.services.fedex_visibility_service import (
    ingest_webhook_payload,
    sync_visibility_from_tracking,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fedex/webhooks", tags=["fedex-visibility"])


def _validate_webhook_secret(x_fedex_webhook_secret: str | None) -> None:
    settings = get_settings()
    expected = (settings.fedex_webhook_secret or "").strip()
    if not expected:
        return
    if (x_fedex_webhook_secret or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Secret webhook FedEx invalide.")


@router.post("/visibility", response_model=WebhookIngestResponse)
async def receive_visibility_webhook(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    x_fedex_webhook_secret: str | None = Header(default=None, alias="X-Fedex-Webhook-Secret"),
) -> WebhookIngestResponse:
    """
    Point d'entrée compatible webhook FedEx Advanced Integrated Visibility.
    En production : FedEx POST ici. En dev : le simulateur peut aussi poster.
    """
    _validate_webhook_secret(x_fedex_webhook_secret)
    created = ingest_webhook_payload(db, payload, source="fedex_webhook", commit=True)
    tracking_numbers = sorted({row.tracking_number for row in created})
    write_log(
        db,
        action="fedex.visibility.webhook",
        message=f"Webhook FedEx Visibility : {len(created)} événement(s)",
        category="system",
        level="INFO",
        ip_address=client_ip(request),
        metadata={"tracking_numbers": tracking_numbers, "count": len(created)},
        commit=True,
    )
    return WebhookIngestResponse(
        accepted=len(created),
        tracking_numbers=tracking_numbers,
        message=f"{len(created)} événement(s) enregistré(s).",
    )


@router.post("/visibility/simulate/{tracking_number}", response_model=WebhookIngestResponse)
def simulate_visibility_from_tracking(
    tracking_number: str,
    request: Request,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> WebhookIngestResponse:
    """Admin : synchronise les scanEvents Tracking vers le flux Visibility (simulateur)."""
    settings = get_settings()
    if not settings.fedex_visibility_simulation_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Simulateur Visibility désactivé.")

    try:
        data = fedex_service.get_shipment(tracking_number)
    except fedex_service.TrackingLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    created = sync_visibility_from_tracking(db, data, source="fedex_simulator", commit=True)
    write_log(
        db,
        action="fedex.visibility.simulate",
        message=f"Simulation Visibility pour {tracking_number}",
        category="system",
        level="INFO",
        ip_address=client_ip(request),
        metadata={"tracking_number": tracking_number, "count": len(created)},
        commit=True,
    )
    return WebhookIngestResponse(
        accepted=len(created),
        tracking_numbers=[data["tracking_number"]],
        message=f"{len(created)} événement(s) synchronisé(s) depuis Tracking.",
    )

