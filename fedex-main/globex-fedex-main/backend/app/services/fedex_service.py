import json
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.services.fedex_sandbox_whitelist import (
    FedExSandboxWhitelistError,
    assert_sandbox_whitelist,
)

__all__ = ["TrackingLookupError", "FedExSandboxWhitelistError", "get_shipment", "get_access_token", "normalize_tracking_number", "shipment_to_json_str"]


class TrackingLookupError(Exception):
    """Raised when shipment tracking cannot be resolved."""


_TOKEN_CACHE: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def normalize_tracking_number(tracking_number: str) -> str:
    return tracking_number.strip().upper()


def _normalize_tracking_number(tracking_number: str) -> str:
    return normalize_tracking_number(tracking_number)


def _build_timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=5.0,
        read=settings.fedex_timeout_seconds,
        write=20.0,
        pool=5.0,
    )


def _is_not_found(payload: dict[str, Any]) -> bool:
    output = payload.get("output")
    if not isinstance(output, dict):
        return False
    alerts = output.get("alerts")
    if isinstance(alerts, str):
        return "TRACKING.DATA.NOTFOUND" in alerts
    if isinstance(alerts, list):
        for alert in alerts:
            if isinstance(alert, dict) and str(alert.get("code", "")).upper() == "TRACKING.DATA.NOTFOUND":
                return True
            if isinstance(alert, str) and "TRACKING.DATA.NOTFOUND" in alert:
                return True
    return False


def _extract_track_result(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise TrackingLookupError("Réponse FedEx invalide.")

    complete = output.get("completeTrackResults")
    if isinstance(complete, list):
        for item in complete:
            if isinstance(item, dict):
                track_results = item.get("trackResults")
                if isinstance(track_results, list) and track_results:
                    first = track_results[0]
                    if isinstance(first, dict):
                        return first

    direct = output.get("trackResults")
    if isinstance(direct, list) and direct:
        first = direct[0]
        if isinstance(first, dict):
            return first

    if _is_not_found(payload):
        raise TrackingLookupError("Numéro de suivi introuvable chez FedEx.")
    raise TrackingLookupError("Aucune donnée de suivi renvoyée par FedEx.")


def _extract_scan_location_parts(scan_location: Any) -> dict[str, str | None]:
    if not isinstance(scan_location, dict):
        return {"city": None, "state_or_province": None, "country": None, "label": None}
    city = scan_location.get("city")
    state = scan_location.get("stateOrProvinceCode")
    country_code = scan_location.get("countryCode")
    country_name = scan_location.get("countryName")
    country = country_name or country_code
    parts = [p for p in [city, state, country] if isinstance(p, str) and p.strip()]
    label = ", ".join(parts) if parts else None
    return {
        "city": city if isinstance(city, str) else None,
        "state_or_province": state if isinstance(state, str) else None,
        "country": country if isinstance(country, str) else None,
        "country_code": country_code if isinstance(country_code, str) else None,
        "country_name": country_name if isinstance(country_name, str) else None,
        "label": label,
    }


def _format_contact_address(block: Any) -> str | None:
    if not isinstance(block, dict):
        return None
    address = block.get("address")
    if not isinstance(address, dict):
        address = block.get("locationContactAndAddress", {})
        if isinstance(address, dict):
            address = address.get("address")
    if not isinstance(address, dict):
        return None
    street_lines = address.get("streetLines")
    lines: list[str] = []
    if isinstance(street_lines, list):
        lines.extend(str(line).strip() for line in street_lines if str(line).strip())
    for key in ("city", "stateOrProvinceCode", "postalCode", "countryName", "countryCode"):
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(value.strip())
    return ", ".join(lines) if lines else None


def _extract_date_by_type(track_result: dict[str, Any], date_type: str) -> str | None:
    date_and_times = track_result.get("dateAndTimes")
    if not isinstance(date_and_times, list):
        return None
    for item in date_and_times:
        if isinstance(item, dict) and item.get("type") == date_type:
            value = item.get("dateTime")
            if isinstance(value, str) and value.strip():
                return value
    return None


def _extract_location(track_result: dict[str, Any]) -> str | None:
    latest = track_result.get("latestStatusDetail")
    if isinstance(latest, dict):
        return _extract_scan_location_parts(latest.get("scanLocation")).get("label")
    return None


def _extract_estimated_delivery(track_result: dict[str, Any]) -> str | None:
    return _extract_date_by_type(track_result, "ESTIMATED_DELIVERY")


def _extract_actual_delivery(track_result: dict[str, Any]) -> str | None:
    return _extract_date_by_type(track_result, "ACTUAL_DELIVERY")


def _extract_events(track_result: dict[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    scan_events = track_result.get("scanEvents")
    if not isinstance(scan_events, list):
        return events

    for item in scan_events:
        if not isinstance(item, dict):
            continue
        at = item.get("date") or item.get("dateTime")
        description = item.get("eventDescription") or item.get("derivedStatus") or "Événement de suivi"
        loc_parts = _extract_scan_location_parts(item.get("scanLocation"))
        events.append(
            {
                "at": str(at) if at is not None else "",
                "description": str(description),
                "location": loc_parts.get("label") or "",
                "city": loc_parts.get("city") or "",
                "state_or_province": loc_parts.get("state_or_province") or "",
                "country": loc_parts.get("country") or "",
                "country_code": loc_parts.get("country_code") or "",
                "country_name": loc_parts.get("country_name") or "",
                "event_type": str(item.get("eventType") or item.get("derivedStatusCode") or ""),
                "status_code": str(item.get("exceptionCode") or item.get("derivedStatusCode") or ""),
            }
        )
    events.sort(key=lambda e: e.get("at") or "", reverse=True)
    return events


def _format_weight_value(block: Any) -> str | None:
    if isinstance(block, list) and block:
        first = block[0]
        if isinstance(first, dict):
            return _format_weight_value(first)
        return None
    if not isinstance(block, dict):
        return None
    value = block.get("value") or block.get("amount")
    unit = block.get("unit") or block.get("units")
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if unit:
        return f"{text} {unit}".strip()
    return text


def _format_dimensions(block: Any) -> str | None:
    if block is None:
        return None
    if isinstance(block, list) and block:
        first = block[0]
        if isinstance(first, dict):
            return _format_dimensions(first)
        return None
    if not isinstance(block, dict):
        return None
    length = block.get("length") or block.get("lengthValue")
    width = block.get("width") or block.get("widthValue")
    height = block.get("height") or block.get("heightValue")
    unit = block.get("unit") or block.get("units") or block.get("dimensionUnit")
    parts: list[str] = []
    for val in (length, width, height):
        if val is not None and str(val).strip():
            parts.append(str(val).strip())
    if len(parts) < 2:
        return None
    label = " × ".join(parts[:3])
    if unit:
        return f"{label} {unit}".strip()
    return label


def _extract_package_info(track_result: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    weight: str | None = None
    dimensions: str | None = None
    package_type: str | None = None
    package_count: str | None = None

    package_details = track_result.get("packageDetails")
    if isinstance(package_details, dict):
        packaging = package_details.get("packagingDescription")
        if isinstance(packaging, dict):
            package_type = packaging.get("description") or packaging.get("type")
        if package_type is None:
            package_type = package_details.get("physicalPackagingType")
        count = package_details.get("count")
        if count is not None:
            package_count = str(count)

    for key in ("packageDetails", "shipmentDetails", "additionalTrackingInfo"):
        block = track_result.get(key)
        if not isinstance(block, dict):
            continue
        wd = block.get("weightAndDimensions")
        if isinstance(wd, dict):
            if weight is None:
                weight = _format_weight_value(wd.get("weight")) or _format_weight_value(
                    wd.get("packageWeight")
                )
            if dimensions is None:
                dimensions = _format_dimensions(wd.get("dimensions")) or _format_dimensions(wd)
        if weight is None:
            weight = _format_weight_value(block.get("weight")) or _format_weight_value(
                block.get("packageWeight")
            )
        if dimensions is None:
            dimensions = _format_dimensions(block.get("dimensions"))

    if weight is None:
        weight = _format_weight_value(track_result.get("packageWeight"))
    if dimensions is None:
        dimensions = _format_dimensions(track_result.get("dimensions"))

    return weight, dimensions, package_type, package_count


def _normalize_special_handlings(track_result: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw = track_result.get("specialHandlings")
    if not isinstance(raw, list):
        return items
    for row in raw:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "type": str(row.get("type") or ""),
                "description": str(row.get("description") or ""),
                "payment_type": str(row.get("paymentType") or ""),
            }
        )
    return items


def _normalize_available_images(track_result: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    raw = track_result.get("availableImages")
    if not isinstance(raw, list):
        return images
    for row in raw:
        if isinstance(row, dict):
            images.append(
                {
                    "type": str(row.get("type") or ""),
                    "size": str(row.get("size") or ""),
                }
            )
        elif isinstance(row, str) and row.strip():
            images.append({"type": row.strip(), "size": ""})
    return images


def _extract_received_by_name(track_result: dict[str, Any]) -> str | None:
    delivery = track_result.get("deliveryDetails")
    if isinstance(delivery, dict):
        name = delivery.get("receivedByName") or delivery.get("signedByName")
        if isinstance(name, str) and name.strip():
            return name.strip()
    recipient = track_result.get("recipientInformation")
    if isinstance(recipient, dict):
        contact = recipient.get("contact")
        if isinstance(contact, dict):
            name = contact.get("personName") or contact.get("companyName")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _map_tracking_payload(payload: dict[str, Any], normalized_tracking: str) -> dict[str, Any]:
    track_result = _extract_track_result(payload)

    tracking_number = normalized_tracking
    tni = track_result.get("trackingNumberInfo")
    if isinstance(tni, dict):
        tn = tni.get("trackingNumber")
        if isinstance(tn, str) and tn.strip():
            tracking_number = tn.strip().upper()

    latest = track_result.get("latestStatusDetail") if isinstance(track_result, dict) else None
    status: str | None = None
    status_code: str | None = None
    status_description: str | None = None
    loc_parts = {"city": None, "state_or_province": None, "country": None, "label": None}
    if isinstance(latest, dict):
        status = latest.get("description") or latest.get("statusByLocale")
        status_code = latest.get("code") or latest.get("derivedCode")
        status_description = latest.get("description")
        loc_parts = _extract_scan_location_parts(latest.get("scanLocation"))

    weight, dimensions, package_type, package_count = _extract_package_info(track_result)
    service_detail = track_result.get("serviceDetail") if isinstance(track_result.get("serviceDetail"), dict) else {}
    service_commit = (
        track_result.get("serviceCommitMessage")
        if isinstance(track_result.get("serviceCommitMessage"), dict)
        else {}
    )
    hold_at = track_result.get("holdAtLocation") if isinstance(track_result.get("holdAtLocation"), dict) else None
    delivery_details = (
        track_result.get("deliveryDetails") if isinstance(track_result.get("deliveryDetails"), dict) else None
    )
    available_notifications = track_result.get("availableNotifications")
    if not isinstance(available_notifications, list):
        available_notifications = []

    return {
        "tracking_number": tracking_number,
        "status": status or "Inconnu",
        "status_code": status_code,
        "status_description": status_description,
        "current_location": loc_parts.get("label") or "N/A",
        "city": loc_parts.get("city"),
        "state_or_province": loc_parts.get("state_or_province"),
        "country": loc_parts.get("country"),
        "estimated_delivery": _extract_estimated_delivery(track_result) or "N/A",
        "actual_delivery": _extract_actual_delivery(track_result),
        "events": _extract_events(track_result),
        "service_type": service_detail.get("type"),
        "service_description": service_detail.get("description") or service_detail.get("shortDescription"),
        "shipper": _format_contact_address(track_result.get("shipperInformation")),
        "recipient": _format_contact_address(track_result.get("recipientInformation")),
        "origin_location": _format_contact_address(track_result.get("originLocation")),
        "destination_location": _format_contact_address(
            track_result.get("destinationLocation")
            or track_result.get("lastUpdatedDestinationAddress")
        ),
        "weight": weight,
        "dimensions": dimensions,
        "package_type": package_type,
        "package_count": package_count,
        "special_handlings": _normalize_special_handlings(track_result),
        "delivery_details": delivery_details,
        "received_by_name": _extract_received_by_name(track_result),
        "available_images": _normalize_available_images(track_result),
        "available_notifications": [str(n) for n in available_notifications if n],
        "hold_at_location": hold_at,
        "service_commit_message": service_commit.get("message") if service_commit else None,
        "source": "fedex_api",
        "raw": payload,
    }


def get_access_token(force_refresh: bool = False) -> str:
    return _get_access_token(force_refresh)


def _get_access_token(force_refresh: bool = False) -> str:
    settings = get_settings()
    if not force_refresh:
        cached = _TOKEN_CACHE.get("access_token")
        expires_at = float(_TOKEN_CACHE.get("expires_at") or 0.0)
        if isinstance(cached, str) and cached and time.time() < expires_at - 30:
            return cached

    if not settings.fedex_client_id or not settings.fedex_client_secret:
        raise TrackingLookupError("Configuration FedEx incomplète (client_id/client_secret).")

    endpoint = f"{settings.fedex_base_url.rstrip('/')}/oauth/token"
    body = {
        "grant_type": "client_credentials",
        "client_id": settings.fedex_client_id,
        "client_secret": settings.fedex_client_secret,
    }
    with httpx.Client(timeout=_build_timeout()) as client:
        resp = client.post(
            endpoint,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()

    token = data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise TrackingLookupError("Token FedEx absent de la réponse OAuth.")
    expires_in = int(data.get("expires_in", 3600))
    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = time.time() + max(60, expires_in)
    return token


def _track_by_number(normalized_tracking: str) -> dict[str, Any]:
    settings = get_settings()
    endpoint = f"{settings.fedex_base_url.rstrip('/')}/track/v1/trackingnumbers"

    def _request_with_token(token: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-customer-transaction-id": str(uuid4()),
            "x-locale": settings.fedex_locale,
        }
        body = {
            "includeDetailedScans": True,
            "trackingInfo": [
                {
                    "trackingNumberInfo": {
                        "trackingNumber": normalized_tracking,
                    }
                }
            ],
        }
        with httpx.Client(timeout=_build_timeout()) as client:
            return client.post(endpoint, json=body, headers=headers)

    token = _get_access_token()
    resp = _request_with_token(token)
    if resp.status_code == 401:
        token = _get_access_token(force_refresh=True)
        resp = _request_with_token(token)

    if resp.status_code == 404:
        raise TrackingLookupError("Numéro de suivi introuvable.")
    if resp.status_code >= 400:
        raise TrackingLookupError(f"Erreur FedEx ({resp.status_code}).")

    payload = resp.json()
    return _map_tracking_payload(payload, normalized_tracking)


def _mock_shipment(normalized: str) -> dict[str, Any]:
    return {
        "tracking_number": normalized,
        "status": "En transit",
        "current_location": "Hub Casablanca",
        "estimated_delivery": datetime.utcnow().date().isoformat(),
        "events": [
            {"at": "2026-04-21T10:00:00Z", "description": "Colis reçu au hub", "location": "Casablanca"},
            {"at": "2026-04-20T18:30:00Z", "description": "En route vers destination", "location": "Paris"},
            {"at": "2026-04-20T08:00:00Z", "description": "Pris en charge", "location": "Paris"},
        ],
        "weight": "2.5 KG",
        "dimensions": "30 × 20 × 15 CM",
        "source": "mock_fedex",
    }


def get_shipment(tracking_number: str) -> dict[str, Any]:
    normalized = _normalize_tracking_number(tracking_number)
    settings = get_settings()
    if not settings.fedex_enabled:
        return _mock_shipment(normalized)
    assert_sandbox_whitelist(normalized)
    return _track_by_number(normalized)


def shipment_to_json_str(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)
