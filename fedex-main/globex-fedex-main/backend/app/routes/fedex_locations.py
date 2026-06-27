"""Recherche de centres FedEx via Location Search API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.location import LocationAddressQuery, LocationSearchRequest, LocationSearchResponse
from app.services.activity_log_service import write_log
from app.services.fedex_location_service import LocationSearchError, search_locations
from app.services.quota_service import enforce_daily_quota

router = APIRouter(prefix="/fedex/locations", tags=["fedex-locations"])


@router.post("/search", response_model=LocationSearchResponse)
def search_fedex_locations(
    query: LocationSearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LocationSearchResponse:
    enforce_daily_quota(db, user, kind="trackings")
    try:
        result = search_locations(query)
    except LocationSearchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_log(
        db,
        action="fedex.location_search",
        message="Recherche de centres FedEx",
        category="system",
        level="INFO",
        user_id=user.id,
        metadata={
            "criterion": query.criterion,
            "city": query.address.city if query.address else None,
            "country": query.address.country_code if query.address else None,
            "results": result.results_returned,
        },
        commit=True,
    )
    return result


@router.get("/search", response_model=LocationSearchResponse)
def search_fedex_locations_get(
    city: str = Query(..., min_length=1),
    country_code: str = Query(..., min_length=2, max_length=2),
    postal_code: str | None = None,
    state_or_province_code: str | None = None,
    street: str | None = None,
    radius_miles: float = Query(default=25.0, ge=1.0, le=50.0),
    max_results: int = Query(default=10, ge=1, le=75),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LocationSearchResponse:
    street_lines = [street] if street and street.strip() else []
    query = LocationSearchRequest(
        criterion="ADDRESS",
        address=LocationAddressQuery(
            street_lines=street_lines,
            city=city,
            state_or_province_code=state_or_province_code,
            postal_code=postal_code,
            country_code=country_code.upper(),
        ),
        radius_miles=radius_miles,
        max_results=max_results,
    )
    return search_fedex_locations(query, db=db, user=user)
