"""Téléchargement et métadonnées de preuve de livraison FedEx (SPOD / POD PDF)."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.services.fedex_service import TrackingLookupError, get_access_token, get_shipment, normalize_tracking_number
from app.services.pod_pdf_service import generate_pod_pdf

logger = logging.getLogger(__name__)

_DELIVERED_HINTS = (
    "delivered",
    "livré",
    "livree",
    "livraison effectuée",
    "delivery completed",
    "dl ",
    " dl",
)


def _build_timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=5.0,
        read=settings.fedex_timeout_seconds,
        write=20.0,
        pool=5.0,
    )


def is_likely_delivered(status: str | None, events: list[dict[str, str]] | None = None) -> bool:
    text = (status or "").lower()
    if any(hint in text for hint in _DELIVERED_HINTS):
        return True
    if events:
        for ev in events:
            desc = (ev.get("description") or "").lower()
            if any(hint in desc for hint in _DELIVERED_HINTS):
                return True
    return False


def is_pod_available(shipment_data: dict[str, Any]) -> bool:
    """POD disponible si livré ou si FedEx expose SIGNATURE_PROOF_OF_DELIVERY."""
    if is_likely_delivered(shipment_data.get("status"), shipment_data.get("events")):
        return True
    for img in shipment_data.get("available_images") or []:
        if not isinstance(img, dict):
            continue
        if str(img.get("type") or "").upper() == "SIGNATURE_PROOF_OF_DELIVERY":
            return True
    return False


def _extract_track_result(raw: dict[str, Any]) -> dict[str, Any] | None:
    output = raw.get("output")
    if not isinstance(output, dict):
        return None
    for block in output.get("completeTrackResults") or []:
        if not isinstance(block, dict):
            continue
        for tr in block.get("trackResults") or []:
            if isinstance(tr, dict):
                return tr
    return None


def extract_pod_info_from_shipment(shipment_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extrait les métadonnées POD depuis une réponse tracking mappée."""
    if not is_likely_delivered(shipment_data.get("status"), shipment_data.get("events")):
        return None

    tn = shipment_data.get("tracking_number") or ""
    pod: dict[str, Any] = {
        "tracking_number": str(tn).strip().upper(),
        "status": shipment_data.get("status"),
        "current_location": shipment_data.get("current_location"),
        "delivered_at": None,
        "delivered_time": None,
        "delivery_address": None,
        "received_by_name": None,
        "signature_available": False,
        "carrier_service": None,
        "delivery_notes": None,
        "source": shipment_data.get("source") or "fedex_api",
    }

    raw = shipment_data.get("raw")
    track_result = _extract_track_result(raw) if isinstance(raw, dict) else None

    if track_result:
        delivery = track_result.get("deliveryDetails") or {}
        if isinstance(delivery, dict):
            pod["received_by_name"] = delivery.get("receivedByName")
            addr = delivery.get("actualDeliveryAddress")
            if isinstance(addr, dict):
                parts = [
                    p
                    for p in [
                        ", ".join(addr.get("streetLines") or []) if isinstance(addr.get("streetLines"), list) else None,
                        addr.get("city"),
                        addr.get("stateOrProvinceCode"),
                        addr.get("postalCode"),
                        addr.get("countryName"),
                    ]
                    if isinstance(p, str) and p.strip()
                ]
                pod["delivery_address"] = ", ".join(parts) if parts else None
            pod["delivery_notes"] = delivery.get("locationDescription")

        images = track_result.get("availableImages")
        if isinstance(images, list):
            pod["signature_available"] = any(
                isinstance(img, dict) and img.get("type") == "SIGNATURE_PROOF_OF_DELIVERY" for img in images
            )

        service = track_result.get("serviceDetail")
        if isinstance(service, dict):
            pod["carrier_service"] = service.get("description") or service.get("type")

        for item in track_result.get("dateAndTimes") or []:
            if isinstance(item, dict) and item.get("type") == "ACTUAL_DELIVERY":
                pod["delivered_at"] = item.get("dateTime")
                break

        for scan in track_result.get("scanEvents") or []:
            if not isinstance(scan, dict):
                continue
            if (scan.get("eventType") or "").upper() == "DL" or "delivered" in (
                scan.get("eventDescription") or ""
            ).lower():
                pod["delivered_at"] = pod["delivered_at"] or scan.get("date") or scan.get("dateTime")
                if not pod["delivery_address"]:
                    loc = scan.get("scanLocation")
                    if isinstance(loc, dict):
                        pod["delivery_address"] = ", ".join(
                            p
                            for p in [loc.get("city"), loc.get("stateOrProvinceCode"), loc.get("countryName")]
                            if isinstance(p, str) and p.strip()
                        ) or None
                break

    if not pod["delivered_at"]:
        for ev in shipment_data.get("events") or []:
            if "delivered" in (ev.get("description") or "").lower():
                pod["delivered_at"] = ev.get("at")
                if not pod["delivery_address"] and ev.get("location"):
                    pod["delivery_address"] = ev.get("location")
                break

    if pod["delivered_at"] and "T" in str(pod["delivered_at"]):
        pod["delivered_time"] = str(pod["delivered_at"]).split("T", 1)[-1][:8]

    if not pod["delivery_address"]:
        pod["delivery_address"] = shipment_data.get("current_location")

    return pod


def pod_info_from_db_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        **record,
        "source": "fedex_visibility_cache",
    }


def _extract_pdf_bytes(payload: dict[str, Any]) -> bytes:
    def walk(node: Any) -> bytes | None:
        if isinstance(node, dict):
            for key in ("encodedLabel", "documentContent", "content", "image", "url"):
                raw = node.get(key)
                if isinstance(raw, str) and len(raw) > 100:
                    try:
                        return base64.b64decode(raw, validate=False)
                    except (ValueError, TypeError):
                        pass
            for value in node.values():
                found = walk(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        return None

    data = walk(payload)
    if not data:
        raise TrackingLookupError(
            "FedEx n'a pas renvoyé de document PDF pour ce colis."
        )
    if data[:4] != b"%PDF":
        raise TrackingLookupError("Le document renvoyé par FedEx n'est pas un PDF valide.")
    return data


def _fetch_fedex_pod_pdf(normalized: str) -> bytes | None:
    settings = get_settings()
    if not settings.fedex_enabled or not settings.fedex_client_id or not settings.fedex_client_secret:
        return None

    endpoint = f"{settings.fedex_base_url.rstrip('/')}/track/v1/trackingdocuments"
    spec: dict[str, Any] = {"trackingNumberInfo": {"trackingNumber": normalized}}
    if settings.fedex_account_number.strip():
        spec["accountNumber"] = {"value": settings.fedex_account_number.strip()}

    body = {
        "trackDocumentDetail": {
            "documentType": "SIGNATURE_PROOF_OF_DELIVERY",
            "documentFormat": "PDF",
        },
        "trackDocumentSpecification": [spec],
    }

    def _post(token: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-customer-transaction-id": str(uuid4()),
            "x-locale": settings.fedex_locale,
        }
        with httpx.Client(timeout=_build_timeout()) as client:
            return client.post(endpoint, json=body, headers=headers)

    try:
        token = get_access_token()
        resp = _post(token)
        if resp.status_code == 401:
            token = get_access_token(force_refresh=True)
            resp = _post(token)
        if resp.status_code >= 400:
            logger.info("FedEx POD indisponible pour %s (HTTP %s)", normalized, resp.status_code)
            return None
        payload = resp.json()
        return _extract_pdf_bytes(payload)
    except TrackingLookupError:
        return None
    except Exception as exc:
        logger.warning("FedEx POD error for %s: %s", normalized, exc)
        return None


def get_proof_of_delivery_pdf(
    tracking_number: str,
    *,
    pod_info: dict[str, Any] | None = None,
    shipment_data: dict[str, Any] | None = None,
) -> bytes:
    """
    Télécharge le PDF FedEx si disponible, sinon génère un PDF à partir des métadonnées POD.
    """
    normalized = normalize_tracking_number(tracking_number)
    settings = get_settings()

    if not settings.fedex_enabled:
        info = pod_info or (extract_pod_info_from_shipment(shipment_data) if shipment_data else None)
        if not info:
            info = {
                "tracking_number": normalized,
                "status": "Delivered (demo)",
                "delivered_at": "—",
                "delivery_address": "—",
                "received_by_name": "—",
                "signature_available": False,
                "source": "mock_fedex",
            }
        return generate_pod_pdf(info)

    fedex_pdf = _fetch_fedex_pod_pdf(normalized)
    if fedex_pdf:
        return fedex_pdf

    info = pod_info
    resolved_shipment = shipment_data
    if info is None:
        if resolved_shipment is None:
            try:
                resolved_shipment = get_shipment(normalized)
            except TrackingLookupError:
                resolved_shipment = None
        if resolved_shipment:
            info = extract_pod_info_from_shipment(resolved_shipment)
    if info is None:
        raise TrackingLookupError(
            "Preuve de livraison indisponible : le colis n'est pas marqué comme livré ou les métadonnées sont absentes."
        )

    logger.info("Génération PDF POD de secours pour %s", normalized)
    return generate_pod_pdf({**info, "source": info.get("source") or "fedex_tracking_fallback"})


def get_pod_info_for_tracking(
    shipment_data: dict[str, Any] | None,
    db_record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if shipment_data:
        extracted = extract_pod_info_from_shipment(shipment_data)
        if extracted:
            return extracted
    return pod_info_from_db_record(db_record)
