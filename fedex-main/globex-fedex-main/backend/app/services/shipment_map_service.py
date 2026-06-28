"""Carte de suivi : géocodage backend et points à partir des scanEvents FedEx."""

from __future__ import annotations

import re
from typing import Any

# Villes sandbox FedEx + hubs courants (coordonnées approximatives pour démo)
_SANDBOX_CITY_COORDS: dict[str, tuple[float, float]] = {
    "greenwood": (39.6137, -86.1067),
    "bronx": (40.8448, -73.8648),
    "miami": (25.7617, -80.1918),
    "new castle": (39.6629, -75.5666),
    "sacramento": (38.5816, -121.4944),
    "fort worth": (32.7555, -97.3308),
    "roissy": (49.0097, 2.5479),
    "roissy cdg": (49.0097, 2.5479),
    "cdg": (49.0097, 2.5479),
    "orlando": (28.5383, -81.3792),
    "newark": (40.7357, -74.1724),
    "indianapolis": (39.7684, -86.1581),
    "memphis": (35.1495, -90.049),
    "louisville": (38.2527, -85.7585),
    "paris": (48.8566, 2.3522),
    "casablanca": (33.5731, -7.5898),
    "new york": (40.7128, -74.006),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "atlanta": (33.749, -84.388),
    "dallas": (32.7767, -96.797),
    "london": (51.5074, -0.1278),
}

_US_STATE_DEFAULTS: dict[str, tuple[float, float]] = {
    "IN": (39.7684, -86.1581),
    "NY": (40.7128, -74.006),
    "FL": (28.5383, -81.3792),
    "CA": (38.5816, -121.4944),
    "TX": (32.7555, -97.3308),
    "TN": (35.1495, -90.049),
    "KY": (38.2527, -85.7585),
    "DE": (39.7391, -75.5398),
    "NJ": (40.7357, -74.1724),
}


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def geocode_location(
    *,
    city: str | None = None,
    state_or_province: str | None = None,
    country_code: str | None = None,
    location_label: str | None = None,
) -> tuple[float, float] | None:
    """Géocodage local — jamais d'appel externe avec clé secrète."""
    candidates: list[str] = []
    if city:
        candidates.append(_normalize_key(city))
    if location_label:
        candidates.append(_normalize_key(location_label))

    for text in candidates:
        if not text:
            continue
        best: tuple[str, tuple[float, float]] | None = None
        for key, coords in _SANDBOX_CITY_COORDS.items():
            if key in text:
                if best is None or len(key) > len(best[0]):
                    best = (key, coords)
        if best:
            return best[1]

    state = (state_or_province or "").strip().upper()
    if state and state in _US_STATE_DEFAULTS:
        return _US_STATE_DEFAULTS[state]

    if country_code and country_code.upper() == "FR":
        return (48.8566, 2.3522)
    if country_code and country_code.upper() == "US":
        return (39.8283, -98.5795)

    return None


def _is_delivered_status(status: str | None) -> bool:
    s = (status or "").lower()
    return any(k in s for k in ("deliver", "livré", "livree", "livre"))


def _is_delivered_event(description: str) -> bool:
    d = (description or "").lower()
    return any(k in d for k in ("delivered", "livré", "livree", "delivery"))


def _offset_duplicate(lat: float, lng: float, index: int) -> tuple[float, float]:
    """Décale légèrement les marqueurs au même endroit."""
    return lat + (index % 4) * 0.012, lng + (index // 4) * 0.012


def _split_country(country: str | None) -> tuple[str, str]:
    raw = (country or "").strip()
    if not raw:
        return "", ""
    if len(raw) <= 3 and raw.isalpha():
        return raw.upper(), raw.upper()
    return "", raw


def build_map_points(
    events: list[dict[str, Any]] | None,
    *,
    current_location: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    Points chronologiques (ancien → récent) pour la carte Leaflet.
    Chaque scanEvent FedEx avec localisation devient une étape numérotée.
    """
    delivered = _is_delivered_status(status)
    chronological = list(reversed(events or []))
    if not chronological and current_location:
        chronological = [
            {
                "at": "",
                "description": "Position actuelle",
                "location": current_location,
            }
        ]

    points: list[dict[str, Any]] = []
    coord_usage: dict[tuple[float, float], int] = {}

    for idx, ev in enumerate(chronological, start=1):
        city = str(ev.get("city") or "").strip()
        state = str(ev.get("state_or_province") or ev.get("stateOrProvinceCode") or "").strip()
        country_raw = str(ev.get("country") or ev.get("countryName") or "").strip()
        country_code = str(ev.get("country_code") or ev.get("countryCode") or "").strip()
        country_name = str(ev.get("country_name") or ev.get("countryName") or "").strip()
        if not country_code and not country_name:
            country_code, country_name = _split_country(country_raw)
        elif country_code and not country_name:
            country_name = country_raw or country_code
        elif country_name and not country_code:
            cc, cn = _split_country(country_name)
            country_code = cc or country_code
            country_name = cn or country_name

        location_label = str(ev.get("location") or "").strip()
        if not location_label:
            parts = [p for p in (city, state, country_name or country_code) if p]
            location_label = ", ".join(parts)

        if not location_label:
            continue

        coords = geocode_location(
            city=city or None,
            state_or_province=state or None,
            country_code=country_code or None,
            location_label=location_label,
        )

        lat: float | None = None
        lng: float | None = None
        if coords:
            base_lat, base_lng = coords
            key = (round(base_lat, 3), round(base_lng, 3))
            usage = coord_usage.get(key, 0)
            coord_usage[key] = usage + 1
            lat, lng = _offset_duplicate(base_lat, base_lng, usage)

        is_last = idx == len(chronological)
        description = str(ev.get("description") or ev.get("eventDescription") or "Événement")
        kind = "transit"
        if is_last and (delivered or _is_delivered_event(description)):
            kind = "delivered"
        elif is_last:
            kind = "current"
        elif idx == 1:
            kind = "origin"

        points.append(
            {
                "step": idx,
                "date": str(ev.get("at") or ev.get("date") or ""),
                "eventDescription": description,
                "city": city,
                "stateOrProvinceCode": state,
                "countryCode": country_code,
                "countryName": country_name or country_code,
                "latitude": lat,
                "longitude": lng,
                "kind": kind,
                "label": location_label,
            }
        )

    return points


def build_tracking_map_payload(
    shipment: dict[str, Any],
    *,
    show_tracking_map: bool = False,
) -> dict[str, Any]:
    """Payload structuré carte + événements pour le chat / API."""
    events = shipment.get("events") or []
    map_points = build_map_points(
        events,
        current_location=shipment.get("current_location"),
        status=shipment.get("status"),
    )
    map_available = any(
        p.get("latitude") is not None and p.get("longitude") is not None for p in map_points
    )
    delivered = _is_delivered_status(shipment.get("status"))
    if map_points and map_points[-1].get("kind") == "delivered":
        delivered = True

    return {
        "map_points": map_points,
        "map_available": map_available,
        "show_tracking_map": show_tracking_map,
        "delivered": delivered,
        "tracking_map": {
            "trackingNumber": shipment.get("tracking_number"),
            "status": shipment.get("status"),
            "currentLocation": shipment.get("current_location"),
            "events": events,
            "mapPoints": map_points,
            "map_available": map_available,
            "delivered": delivered,
        },
    }


# Alias rétrocompatibilité
def build_map_points_legacy(events, **kwargs):
    return build_map_points(events, **kwargs)
