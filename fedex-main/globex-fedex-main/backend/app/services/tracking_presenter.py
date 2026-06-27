"""Construction des réponses API / chat à partir des données FedEx mappées."""

from __future__ import annotations

from typing import Any

from app.services.shipment_map_service import build_tracking_map_payload
from app.schemas.tracking import TrackingResponse
from app.schemas.visibility import PodInfoSchema


def shipment_summary(
    data: dict[str, Any],
    *,
    extras: dict[str, Any] | None = None,
    show_tracking_map: bool = False,
    show_timeline: bool = False,
    max_timeline_events: int = 0,
) -> dict[str, Any]:
    extras = extras or {}
    full_events = data.get("events") or []
    if show_timeline:
        limit = max_timeline_events if max_timeline_events > 0 else 8
        events_for_client = full_events[:limit]
    else:
        events_for_client = []

    map_bundle = build_tracking_map_payload(data, show_tracking_map=show_tracking_map)
    if not show_tracking_map:
        map_bundle["map_points"] = []
        map_bundle["map_available"] = False
        map_bundle["show_tracking_map"] = False
        if map_bundle.get("tracking_map"):
            map_bundle["tracking_map"]["mapPoints"] = []
            if not show_timeline:
                map_bundle["tracking_map"]["events"] = []

    summary = {
        "tracking_number": data["tracking_number"],
        "status": data.get("status"),
        "status_code": data.get("status_code"),
        "status_description": data.get("status_description"),
        "current_location": data.get("current_location"),
        "city": data.get("city"),
        "state_or_province": data.get("state_or_province"),
        "country": data.get("country"),
        "estimated_delivery": data.get("estimated_delivery"),
        "actual_delivery": data.get("actual_delivery"),
        "events": events_for_client,
        "timeline_total": len(full_events),
        "show_timeline": show_timeline,
        "visibility_events": (extras.get("visibility_events") or []) if show_timeline else [],
        "service_type": data.get("service_type"),
        "service_description": data.get("service_description"),
        "shipper": data.get("shipper"),
        "recipient": data.get("recipient"),
        "origin_location": data.get("origin_location"),
        "destination_location": data.get("destination_location"),
        "weight": data.get("weight"),
        "dimensions": data.get("dimensions"),
        "package_type": data.get("package_type"),
        "package_count": data.get("package_count"),
        "special_handlings": data.get("special_handlings") or [],
        "delivery_details": data.get("delivery_details"),
        "received_by_name": data.get("received_by_name"),
        "available_images": data.get("available_images") or [],
        "available_notifications": data.get("available_notifications") or [],
        "hold_at_location": data.get("hold_at_location"),
        "service_commit_message": data.get("service_commit_message"),
        "pod_available": extras.get("pod_available", False),
        "pod_info": extras.get("pod_info"),
        "source": data.get("source"),
        "sandbox_whitelist_denied": False,
        **map_bundle,
    }
    return summary


def minimal_shipment_summary(
    data: dict[str, Any],
    *,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Carte colis minimale (statut + localisation) pour le chat / agent."""
    return shipment_summary(
        data,
        extras=extras,
        show_tracking_map=False,
        show_timeline=False,
        max_timeline_events=0,
    )


def build_tracking_response(data: dict[str, Any], extras: dict[str, Any]) -> TrackingResponse:
    pod_info = extras.get("pod_info")
    pod_schema = PodInfoSchema(**pod_info) if pod_info else None
    return TrackingResponse(
        tracking_number=data["tracking_number"],
        status=data.get("status"),
        status_code=data.get("status_code"),
        status_description=data.get("status_description"),
        current_location=data.get("current_location"),
        city=data.get("city"),
        state_or_province=data.get("state_or_province"),
        country=data.get("country"),
        estimated_delivery=data.get("estimated_delivery"),
        actual_delivery=data.get("actual_delivery"),
        events=data.get("events") or [],
        visibility_events=extras.get("visibility_events") or [],
        service_type=data.get("service_type"),
        service_description=data.get("service_description"),
        shipper=data.get("shipper"),
        recipient=data.get("recipient"),
        origin_location=data.get("origin_location"),
        destination_location=data.get("destination_location"),
        weight=data.get("weight"),
        dimensions=data.get("dimensions"),
        package_type=data.get("package_type"),
        package_count=data.get("package_count"),
        special_handlings=data.get("special_handlings") or [],
        delivery_details=data.get("delivery_details"),
        received_by_name=data.get("received_by_name"),
        available_images=data.get("available_images") or [],
        available_notifications=data.get("available_notifications") or [],
        hold_at_location=data.get("hold_at_location"),
        service_commit_message=data.get("service_commit_message"),
        pod_available=extras.get("pod_available", False),
        pod_info=pod_schema,
        source=data.get("source"),
        details=data,
    )
