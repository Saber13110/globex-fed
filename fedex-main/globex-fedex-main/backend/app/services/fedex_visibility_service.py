"""Advanced Integrated Visibility — ingestion webhook et simulateur."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.fedex_visibility_event import FedexVisibilityEvent
from app.models.shipment_cache import ShipmentCache
from app.models.shipment_pod import ShipmentPod
from app.services.proof_of_delivery_service import extract_pod_info_from_shipment, is_likely_delivered

logger = logging.getLogger(__name__)

VISIBILITY_EVENT_TYPES = (
    "SHIPMENT_CREATED",
    "IN_TRANSIT",
    "ARRIVED_AT_FACILITY",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "DELIVERY_EXCEPTION",
    "CLEARANCE_DELAY",
    "SHIPMENT_EXCEPTION",
    "READY_FOR_PICKUP",
)

_EVENT_TYPE_LABELS = {
    "SHIPMENT_CREATED": "Shipment created",
    "IN_TRANSIT": "In transit",
    "ARRIVED_AT_FACILITY": "Arrived at facility",
    "OUT_FOR_DELIVERY": "Out for delivery",
    "DELIVERED": "Delivered",
    "DELIVERY_EXCEPTION": "Delivery exception",
    "CLEARANCE_DELAY": "Clearance delay",
    "SHIPMENT_EXCEPTION": "Shipment exception",
    "READY_FOR_PICKUP": "Ready for pickup",
}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _location_from_scan(scan_location: Any) -> str | None:
    if not isinstance(scan_location, dict):
        return None
    city = scan_location.get("city")
    country = scan_location.get("countryName")
    parts = [p for p in [city, country] if isinstance(p, str) and p.strip()]
    return ", ".join(parts) if parts else None


def map_fedex_scan_to_visibility_type(event_code: str | None, description: str | None) -> str:
    code = (event_code or "").upper().strip()
    desc = (description or "").lower()

    if code in {"OC", "IN"} or "information sent" in desc or "initiated" in desc:
        return "SHIPMENT_CREATED"
    if code == "OD" or "vehicle for delivery" in desc:
        return "OUT_FOR_DELIVERY"
    if code == "DL" or desc.strip() == "delivered" or desc.startswith("delivered"):
        return "DELIVERED"
    if code == "DE" or "delivery exception" in desc:
        return "DELIVERY_EXCEPTION"
    if code == "CD" or "clearance delay" in desc or "clearance" in desc:
        return "CLEARANCE_DELAY"
    if code == "SE" or "shipment exception" in desc:
        return "SHIPMENT_EXCEPTION"
    if code in {"HP", "HL"} or "ready for pickup" in desc or "pickup" in desc:
        return "READY_FOR_PICKUP"
    if code == "AR" or "arrived at" in desc or "at local fedex" in desc or "at fedex" in desc:
        return "ARRIVED_AT_FACILITY"
    return "IN_TRANSIT"


def _fingerprint(
    tracking_number: str,
    event_type: str,
    description: str,
    occurred_at: str | None,
    location: str | None,
) -> str:
    raw = "|".join(
        [
            tracking_number.strip().upper(),
            event_type,
            description.strip(),
            (occurred_at or "").strip(),
            (location or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_single_event(
    tracking_number: str,
    *,
    event_type: str | None = None,
    event_code: str | None = None,
    description: str,
    location: str | None = None,
    occurred_at: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tn = tracking_number.strip().upper()
    desc = description.strip() or _EVENT_TYPE_LABELS.get(event_type or "", "Tracking update")
    et = event_type or map_fedex_scan_to_visibility_type(event_code, desc)
    if et not in VISIBILITY_EVENT_TYPES:
        et = "IN_TRANSIT"
    return {
        "tracking_number": tn,
        "event_type": et,
        "event_code": event_code,
        "description": desc,
        "location": location,
        "occurred_at": occurred_at,
        "raw": raw or {},
    }


def parse_webhook_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise un payload webhook FedEx (réel ou simulé) en événements unitaires."""
    events: list[dict[str, Any]] = []

    if "tracking_number" in payload and "event_type" in payload:
        events.append(
            _normalize_single_event(
                str(payload["tracking_number"]),
                event_type=str(payload.get("event_type")),
                event_code=payload.get("event_code"),
                description=str(payload.get("description") or payload.get("event_type")),
                location=payload.get("location"),
                occurred_at=payload.get("occurred_at"),
                raw=payload,
            )
        )
        return events

    tn = (
        payload.get("trackingNumber")
        or payload.get("tracking_number")
        or ""
    )
    if isinstance(tn, str) and tn.strip():
        scan = payload.get("scanEvent") or payload.get("event")
        if isinstance(scan, dict):
            events.append(
                _normalize_single_event(
                    tn,
                    event_code=scan.get("eventType"),
                    description=str(
                        scan.get("eventDescription")
                        or scan.get("description")
                        or scan.get("derivedStatus")
                        or "Tracking update"
                    ),
                    location=_location_from_scan(scan.get("scanLocation")),
                    occurred_at=scan.get("date") or scan.get("dateTime"),
                    raw=payload,
                )
            )
            return events

    output = payload.get("output")
    if isinstance(output, dict):
        complete = output.get("completeTrackResults")
        if isinstance(complete, list):
            for block in complete:
                if not isinstance(block, dict):
                    continue
                block_tn = block.get("trackingNumber") or tn
                track_results = block.get("trackResults")
                if not isinstance(track_results, list):
                    continue
                for tr in track_results:
                    if not isinstance(tr, dict):
                        continue
                    tni = tr.get("trackingNumberInfo") or {}
                    resolved_tn = (
                        tni.get("trackingNumber") if isinstance(tni, dict) else None
                    ) or block_tn
                    if not resolved_tn:
                        continue
                    scan_events = tr.get("scanEvents")
                    if isinstance(scan_events, list):
                        for scan in scan_events:
                            if not isinstance(scan, dict):
                                continue
                            events.append(
                                _normalize_single_event(
                                    str(resolved_tn),
                                    event_code=scan.get("eventType"),
                                    description=str(
                                        scan.get("eventDescription")
                                        or scan.get("derivedStatus")
                                        or "Tracking update"
                                    ),
                                    location=_location_from_scan(scan.get("scanLocation")),
                                    occurred_at=scan.get("date") or scan.get("dateTime"),
                                    raw=scan,
                                )
                            )
    return events


def ingest_visibility_event(
    db: Session,
    *,
    tracking_number: str,
    event_type: str,
    description: str,
    event_code: str | None = None,
    location: str | None = None,
    occurred_at: str | None = None,
    source: str = "fedex_webhook",
    raw_payload: dict[str, Any] | None = None,
    commit: bool = False,
) -> FedexVisibilityEvent | None:
    """Enregistre un événement et met à jour le cache colis (+ POD si livré)."""
    normalized = _normalize_single_event(
        tracking_number,
        event_type=event_type,
        event_code=event_code,
        description=description,
        location=location,
        occurred_at=occurred_at,
        raw=raw_payload,
    )
    fp = _fingerprint(
        normalized["tracking_number"],
        normalized["event_type"],
        normalized["description"],
        normalized["occurred_at"],
        normalized["location"],
    )
    existing = db.scalar(
        select(FedexVisibilityEvent).where(FedexVisibilityEvent.fingerprint == fp)
    )
    if existing is not None:
        return None

    row = FedexVisibilityEvent(
        tracking_number=normalized["tracking_number"],
        event_type=normalized["event_type"],
        event_code=normalized["event_code"],
        description=normalized["description"],
        location=normalized["location"],
        occurred_at=_parse_iso_datetime(normalized["occurred_at"]),
        source=source,
        fingerprint=fp,
        raw_payload_json=json.dumps(raw_payload or normalized["raw"], ensure_ascii=False),
    )
    db.add(row)
    if source != "tracking_sync":
        _apply_event_to_shipment_cache(db, normalized)
    db.flush()
    if source in ("fedex_webhook", "fedex_simulator"):
        from app.services.shipment_watch_service import notify_watchers_for_visibility_event

        notify_watchers_for_visibility_event(db, row, commit=False)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def ingest_webhook_payload(
    db: Session,
    payload: dict[str, Any],
    *,
    source: str = "fedex_webhook",
    commit: bool = True,
) -> list[FedexVisibilityEvent]:
    created: list[FedexVisibilityEvent] = []
    for item in parse_webhook_payload(payload):
        row = ingest_visibility_event(
            db,
            tracking_number=item["tracking_number"],
            event_type=item["event_type"],
            description=item["description"],
            event_code=item.get("event_code"),
            location=item.get("location"),
            occurred_at=item.get("occurred_at"),
            source=source,
            raw_payload=item.get("raw"),
            commit=False,
        )
        if row is not None:
            created.append(row)
    if commit:
        db.commit()
    return created


def _get_shipment_cache_row(db: Session, tracking_number: str) -> ShipmentCache | None:
    """Retrouve le cache colis, y compris une ligne ajoutée mais pas encore flushée."""
    tn = tracking_number.strip().upper()
    row = db.query(ShipmentCache).filter(ShipmentCache.tracking_number == tn).one_or_none()
    if row is not None:
        return row
    for pending in db.new:
        if isinstance(pending, ShipmentCache) and pending.tracking_number == tn:
            return pending
    return None


def _apply_event_to_shipment_cache(db: Session, event: dict[str, Any]) -> None:
    tn = event["tracking_number"]
    cache = _get_shipment_cache_row(db, tn)
    if cache is None:
        cache = ShipmentCache(
            tracking_number=tn,
            raw_response_json=json.dumps({"source": "fedex_visibility", "tracking_number": tn}),
            last_status=event["description"],
            last_location=event.get("location"),
            estimated_delivery=None,
        )
        db.add(cache)
        return
    cache.last_status = event["description"]
    if event.get("location"):
        cache.last_location = event["location"]


def upsert_pod_from_shipment(db: Session, shipment_data: dict[str, Any], *, commit: bool = False) -> ShipmentPod | None:
    pod_info = extract_pod_info_from_shipment(shipment_data)
    if not pod_info:
        return None
    tn = pod_info["tracking_number"]
    row = db.query(ShipmentPod).filter(ShipmentPod.tracking_number == tn).one_or_none()
    if row is None:
        row = ShipmentPod(
            tracking_number=tn,
            status=pod_info.get("status"),
            delivered_at=pod_info.get("delivered_at"),
            delivery_address=pod_info.get("delivery_address"),
            received_by_name=pod_info.get("received_by_name"),
            signature_available="true" if pod_info.get("signature_available") else "false",
            carrier_service=pod_info.get("carrier_service"),
            raw_fedex_json=json.dumps(pod_info, ensure_ascii=False),
        )
        db.add(row)
    else:
        row.status = pod_info.get("status")
        row.delivered_at = pod_info.get("delivered_at")
        row.delivery_address = pod_info.get("delivery_address")
        row.received_by_name = pod_info.get("received_by_name")
        row.signature_available = "true" if pod_info.get("signature_available") else "false"
        row.carrier_service = pod_info.get("carrier_service")
        row.raw_fedex_json = json.dumps(pod_info, ensure_ascii=False)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def sync_visibility_from_tracking(
    db: Session,
    shipment_data: dict[str, Any],
    *,
    source: str = "tracking_sync",
    commit: bool = True,
) -> list[FedexVisibilityEvent]:
    """Simule le flux webhook en important les scanEvents d'un appel Tracking."""
    settings = get_settings()
    if not settings.fedex_visibility_sync_on_track:
        return []

    tn = shipment_data.get("tracking_number")
    if not isinstance(tn, str) or not tn.strip():
        return []

    created: list[FedexVisibilityEvent] = []
    events = shipment_data.get("events") or []
    raw_events = []
    raw = shipment_data.get("raw")
    if isinstance(raw, dict):
        output = raw.get("output") or {}
        if isinstance(output, dict):
            for block in output.get("completeTrackResults") or []:
                if not isinstance(block, dict):
                    continue
                for tr in block.get("trackResults") or []:
                    if isinstance(tr, dict) and isinstance(tr.get("scanEvents"), list):
                        raw_events.extend(tr["scanEvents"])

    scan_list = raw_events if raw_events else events
    for scan in reversed(scan_list):
        if isinstance(scan, dict) and "eventType" in scan:
            desc = scan.get("eventDescription") or scan.get("description") or "Tracking update"
            loc = _location_from_scan(scan.get("scanLocation"))
            if not loc and isinstance(scan.get("location"), str):
                loc = scan.get("location")
            at = scan.get("date") or scan.get("dateTime") or scan.get("at")
            row = ingest_visibility_event(
                db,
                tracking_number=tn,
                event_type=map_fedex_scan_to_visibility_type(scan.get("eventType"), desc),
                event_code=scan.get("eventType"),
                description=str(desc),
                location=loc,
                occurred_at=str(at) if at else None,
                source=source,
                raw_payload=scan,
                commit=False,
            )
        else:
            desc = scan.get("description") if isinstance(scan, dict) else None
            if not desc:
                continue
            row = ingest_visibility_event(
                db,
                tracking_number=tn,
                event_type=map_fedex_scan_to_visibility_type(None, str(desc)),
                description=str(desc),
                location=scan.get("location") if isinstance(scan, dict) else None,
                occurred_at=scan.get("at") if isinstance(scan, dict) else None,
                source=source,
                raw_payload=scan if isinstance(scan, dict) else {},
                commit=False,
            )
        if row is not None:
            created.append(row)

    if is_likely_delivered(shipment_data.get("status"), shipment_data.get("events")):
        upsert_pod_from_shipment(db, shipment_data, commit=False)

    if commit:
        db.commit()
    return created


def list_visibility_events(
    db: Session,
    tracking_number: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    tn = tracking_number.strip().upper()
    rows = db.scalars(
        select(FedexVisibilityEvent)
        .where(FedexVisibilityEvent.tracking_number == tn)
        .order_by(FedexVisibilityEvent.occurred_at.desc().nullslast(), FedexVisibilityEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "tracking_number": r.tracking_number,
            "event_type": r.event_type,
            "event_type_label": _EVENT_TYPE_LABELS.get(r.event_type, r.event_type),
            "event_code": r.event_code,
            "description": r.description,
            "location": r.location,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            "source": r.source,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def get_pod_record(db: Session, tracking_number: str) -> dict[str, Any] | None:
    tn = tracking_number.strip().upper()
    row = db.query(ShipmentPod).filter(ShipmentPod.tracking_number == tn).one_or_none()
    if row is None:
        return None
    return {
        "tracking_number": row.tracking_number,
        "status": row.status,
        "delivered_at": row.delivered_at,
        "delivery_address": row.delivery_address,
        "received_by_name": row.received_by_name,
        "signature_available": row.signature_available == "true",
        "carrier_service": row.carrier_service,
    }
