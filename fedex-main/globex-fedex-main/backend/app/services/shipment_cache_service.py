"""Mise à jour du cache local des colis FedEx."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.shipment_cache import ShipmentCache
from app.services import fedex_service


def upsert_shipment_cache(db: Session, data: dict[str, Any]) -> None:
    tn = data["tracking_number"]
    raw = fedex_service.shipment_to_json_str(data)
    row = db.query(ShipmentCache).filter(ShipmentCache.tracking_number == tn).one_or_none()
    if row is None:
        for pending in db.new:
            if isinstance(pending, ShipmentCache) and pending.tracking_number == tn:
                row = pending
                break
    if row is None:
        row = ShipmentCache(
            tracking_number=tn,
            raw_response_json=raw,
            last_status=data.get("status"),
            last_location=data.get("current_location"),
            estimated_delivery=data.get("estimated_delivery"),
        )
        db.add(row)
    else:
        row.raw_response_json = raw
        row.last_status = data.get("status")
        row.last_location = data.get("current_location")
        row.estimated_delivery = data.get("estimated_delivery")
    db.flush()
