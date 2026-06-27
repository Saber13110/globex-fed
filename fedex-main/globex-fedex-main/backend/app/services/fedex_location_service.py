"""FedEx Location Search API v1 — recherche de centres / points de dépôt."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.schemas.location import (
    FedExLocationHours,
    FedExLocationItem,
    LocationSearchRequest,
    LocationSearchResponse,
)


class LocationSearchError(Exception):
    """Erreur lors de la recherche de centres FedEx."""


_LOCATION_TOKEN_CACHE: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def _build_timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=5.0,
        read=settings.fedex_timeout_seconds,
        write=20.0,
        pool=5.0,
    )


def _location_credentials() -> tuple[str, str]:
    settings = get_settings()
    client_id = (settings.fedex_location_client_id or settings.fedex_client_id or "").strip()
    client_secret = (settings.fedex_location_client_secret or settings.fedex_client_secret or "").strip()
    if not client_id or not client_secret:
        raise LocationSearchError("Configuration FedEx Location incomplète (client_id/client_secret).")
    return client_id, client_secret


def _get_location_access_token(force_refresh: bool = False) -> str:
    if not force_refresh:
        cached = _LOCATION_TOKEN_CACHE.get("access_token")
        expires_at = float(_LOCATION_TOKEN_CACHE.get("expires_at") or 0.0)
        if isinstance(cached, str) and cached and time.time() < expires_at - 30:
            return cached

    settings = get_settings()
    client_id, client_secret = _location_credentials()
    endpoint = f"{settings.fedex_base_url.rstrip('/')}/oauth/token"
    body = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
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
        raise LocationSearchError("Token FedEx absent de la réponse OAuth.")
    expires_in = int(data.get("expires_in", 3600))
    _LOCATION_TOKEN_CACHE["access_token"] = token
    _LOCATION_TOKEN_CACHE["expires_at"] = time.time() + max(60, expires_in)
    return token


def _build_fedex_body(query: LocationSearchRequest) -> dict[str, Any]:
    settings = get_settings()
    body: dict[str, Any] = {
        "locationSearchCriterion": query.criterion,
        "multipleMatchesAction": "RETURN_ALL",
        "sort": {"criteria": "DISTANCE", "order": "ASCENDING"},
        "constraints": {
            "radiusDistance": {"value": query.radius_miles, "units": "MI"},
            "resultsToSkip": query.results_to_skip,
            "maxResults": query.max_results,
        },
    }
    account = (settings.fedex_account_number or "").strip()
    if account:
        body["associatedAccountNumber"] = {"value": account}

    if query.criterion == "ADDRESS":
        if not query.address:
            raise LocationSearchError("Adresse requise pour une recherche par adresse.")
        addr = query.address
        address_block: dict[str, Any] = {"countryCode": addr.country_code.upper()}
        if addr.city:
            address_block["city"] = addr.city
        if addr.state_or_province_code:
            address_block["stateOrProvinceCode"] = addr.state_or_province_code
        if addr.postal_code:
            address_block["postalCode"] = addr.postal_code
        if addr.street_lines:
            address_block["streetLines"] = [line for line in addr.street_lines if line.strip()]
        body["location"] = {"address": address_block}
    elif query.criterion == "GEO":
        if not query.geo:
            raise LocationSearchError("Coordonnées GPS requises pour une recherche géographique.")
        body["location"] = {
            "geoPositionalCoordinates": {
                "latitude": query.geo.latitude,
                "longitude": query.geo.longitude,
            }
        }
    elif query.criterion == "PHONE":
        phone = (query.phone_number or "").strip()
        if not phone:
            raise LocationSearchError("Numéro de téléphone requis pour une recherche par téléphone.")
        body["location"] = {"phoneNumber": phone}

    return body


def _parse_hours(item: dict[str, Any]) -> list[FedExLocationHours]:
    hours: list[FedExLocationHours] = []
    store_hours = item.get("storeHours")
    if not isinstance(store_hours, list):
        return hours
    for row in store_hours:
        if not isinstance(row, dict):
            continue
        hours.append(
            FedExLocationHours(
                day_of_week=str(row.get("dayOfWeek") or ""),
                operational_hours_type=row.get("operationalHoursType"),
                begin_time=row.get("beginTime") or row.get("operationalHours", {}).get("begins")
                if isinstance(row.get("operationalHours"), dict)
                else row.get("beginTime"),
                end_time=row.get("endTime") or row.get("operationalHours", {}).get("ends")
                if isinstance(row.get("operationalHours"), dict)
                else row.get("endTime"),
            )
        )
    return hours


def _parse_services(item: dict[str, Any]) -> list[str]:
    services: list[str] = []
    carrier_list = item.get("carrierDetailList")
    if isinstance(carrier_list, list):
        for carrier in carrier_list:
            if isinstance(carrier, dict):
                code = carrier.get("carrierCodeType")
                if isinstance(code, str) and code.strip():
                    services.append(code.strip())
    location_type = item.get("locationType")
    if isinstance(location_type, str) and location_type.strip():
        services.append(location_type.strip())
    return sorted(set(services))


def _map_location_item(item: dict[str, Any]) -> FedExLocationItem:
    contact = item.get("contactAndAddress") if isinstance(item.get("contactAndAddress"), dict) else {}
    address = contact.get("address") if isinstance(contact.get("address"), dict) else {}
    ancillary = contact.get("addressAncillaryDetail") if isinstance(contact.get("addressAncillaryDetail"), dict) else {}
    contact_info = contact.get("contact") if isinstance(contact.get("contact"), dict) else {}
    geo = item.get("geoPositionalCoordinates") if isinstance(item.get("geoPositionalCoordinates"), dict) else {}

    distance_block = item.get("distance") if isinstance(item.get("distance"), dict) else {}
    distance_value = distance_block.get("value")
    distance_miles: float | None = None
    if distance_value is not None:
        try:
            distance_miles = float(distance_value)
        except (TypeError, ValueError):
            distance_miles = None

    street_lines = address.get("streetLines")
    if not isinstance(street_lines, list):
        street_lines = []

    return FedExLocationItem(
        location_id=str(item.get("locationId") or "") or None,
        display_name=ancillary.get("displayName") or item.get("locationType"),
        location_type=item.get("locationType"),
        distance_miles=distance_miles,
        street_lines=[str(line) for line in street_lines if str(line).strip()],
        city=address.get("city"),
        state_or_province_code=address.get("stateOrProvinceCode"),
        postal_code=address.get("postalCode"),
        country_code=address.get("countryCode"),
        phone_number=contact_info.get("phoneNumber") or contact_info.get("phone"),
        latitude=float(geo["latitude"]) if geo.get("latitude") is not None else None,
        longitude=float(geo["longitude"]) if geo.get("longitude") is not None else None,
        store_hours=_parse_hours(item),
        services=_parse_services(item),
    )


def _map_response(payload: dict[str, Any]) -> LocationSearchResponse:
    output = payload.get("output")
    if not isinstance(output, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                raise LocationSearchError(first.get("message") or "Erreur FedEx Location.")
        raise LocationSearchError("Réponse FedEx Location invalide.")

    locations: list[FedExLocationItem] = []
    detail_list = output.get("locationDetailList")
    if isinstance(detail_list, list):
        for item in detail_list:
            if isinstance(item, dict):
                locations.append(_map_location_item(item))

    matched = output.get("matchedAddress")
    return LocationSearchResponse(
        total_results=int(output.get("totalResults") or len(locations)),
        results_returned=int(output.get("resultsReturned") or len(locations)),
        matched_address=matched if isinstance(matched, dict) else None,
        locations=locations,
        source="fedex_api",
        raw=payload,
    )


def _mock_locations(query: LocationSearchRequest) -> LocationSearchResponse:
    city = "Casablanca"
    country = "MA"
    if query.address:
        city = query.address.city or city
        country = query.address.country_code.upper() or country
    return LocationSearchResponse(
        total_results=2,
        results_returned=2,
        matched_address={"city": city, "countryCode": country},
        locations=[
            FedExLocationItem(
                location_id="MOCK-001",
                display_name="FedEx Authorized ShipCenter",
                location_type="FEDEX_OFFICE",
                distance_miles=1.2,
                street_lines=["Boulevard Zerktouni"],
                city=city,
                country_code=country,
                phone_number="+212 5XX-XXXXXX",
                latitude=33.5731,
                longitude=-7.5898,
                services=["FDXE", "FEDEX_OFFICE"],
            ),
            FedExLocationItem(
                location_id="MOCK-002",
                display_name="FedEx Drop Box",
                location_type="FEDEX_DROP_BOX",
                distance_miles=2.8,
                street_lines=["Avenue des FAR"],
                city=city,
                country_code=country,
                services=["FDXE", "FEDEX_DROP_BOX"],
            ),
        ],
        source="mock_fedex_location",
    )


def search_locations(query: LocationSearchRequest) -> LocationSearchResponse:
    settings = get_settings()
    if not settings.fedex_enabled:
        return _mock_locations(query)

    endpoint = f"{settings.fedex_base_url.rstrip('/')}/location/v1/locations"
    body = _build_fedex_body(query)

    def _request_with_token(token: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-customer-transaction-id": str(uuid4()),
            "x-locale": settings.fedex_locale,
        }
        with httpx.Client(timeout=_build_timeout()) as client:
            return client.post(endpoint, json=body, headers=headers)

    token = _get_location_access_token()
    resp = _request_with_token(token)
    if resp.status_code == 401:
        token = _get_location_access_token(force_refresh=True)
        resp = _request_with_token(token)

    if resp.status_code >= 400:
        try:
            payload = resp.json()
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict) and first.get("message"):
                    raise LocationSearchError(str(first["message"]))
        except LocationSearchError:
            raise
        except Exception:
            pass
        raise LocationSearchError(f"Erreur FedEx Location ({resp.status_code}).")

    return _map_response(resp.json())
