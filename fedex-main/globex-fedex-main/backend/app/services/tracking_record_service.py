"""Persistance historique suivi — table tracking_requests."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.tracking_request import TrackingRequest
from app.services import fedex_service
from app.services.chat_export_service import latest_tracking_rows
from app.services.fedex_sandbox_whitelist import FedExSandboxWhitelistError
from app.services.fedex_service import TrackingLookupError

logger = logging.getLogger(__name__)


def persist_tracking_request(
    db: Session,
    *,
    user_id: int,
    session_id: int | None,
    tracking_number: str,
    user_question: str,
    bot_response: str,
    shipment_data: dict[str, Any] | None = None,
) -> TrackingRequest:
    """Enregistre un tour de suivi pour export PDF/Excel et historique session."""
    tn = (tracking_number or "").strip().upper()
    if not tn:
        raise ValueError("tracking_number requis")

    data = shipment_data or {}
    tr = TrackingRequest(
        user_id=user_id,
        session_id=session_id,
        tracking_number=tn,
        user_question=(user_question or "").strip() or "(sans question)",
        bot_response=(bot_response or "").strip() or "(sans réponse)",
        status=data.get("status"),
        current_location=data.get("current_location"),
        estimated_delivery=data.get("estimated_delivery"),
    )
    db.add(tr)
    db.flush()
    return tr


def shipment_data_from_turn(
    shipment: dict[str, Any] | None,
    *,
    tracking_number: str | None = None,
) -> dict[str, Any] | None:
    """Reconstruit un dict shipment_data minimal depuis la carte client."""
    if not shipment:
        return None
    tn = (shipment.get("tracking_number") or tracking_number or "").strip()
    if not tn:
        return None
    return {
        "tracking_number": tn,
        "status": shipment.get("status"),
        "current_location": shipment.get("current_location"),
        "estimated_delivery": shipment.get("estimated_delivery"),
    }


def ensure_tracking_in_db_for_export(
    db: Session,
    *,
    user_id: int,
    session_id: int | None,
    tracking_number: str,
    user_message: str,
) -> tuple[bool, str | None]:
    """
    Garantit une ligne tracking_requests pour export PDF.
    Retourne (succès, message_erreur optionnel).
    """
    tn = (tracking_number or "").strip().upper()
    if not tn:
        return False, "missing_tracking"

    rows = latest_tracking_rows(
        db,
        user_id=user_id,
        session_id=session_id,
        tracking_numbers=[tn],
        limit=1,
    )
    if rows:
        return True, None

    try:
        shipment_data = fedex_service.get_shipment(tn)
    except FedExSandboxWhitelistError:
        return False, "sandbox_denied"
    except TrackingLookupError:
        return False, "not_found"
    except Exception:
        logger.exception("FedEx indisponible pour export PDF tn=%s", tn[:4])
        return False, "fedex_unavailable"

    status = str(shipment_data.get("status") or "inconnu")
    preview = f"Colis {tn} — {status}"
    try:
        persist_tracking_request(
            db,
            user_id=user_id,
            session_id=session_id,
            tracking_number=tn,
            user_question=user_message,
            bot_response=preview,
            shipment_data=shipment_data,
        )
    except Exception:
        logger.exception("persist_tracking_request failed tn=%s", tn[:4])
        return False, "persist_failed"

    return True, None
