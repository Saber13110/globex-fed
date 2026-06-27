from typing import Any, Literal

from pydantic import BaseModel, Field


class LocationAddressQuery(BaseModel):
    street_lines: list[str] = Field(default_factory=list)
    city: str | None = None
    state_or_province_code: str | None = None
    postal_code: str | None = None
    country_code: str = Field(min_length=2, max_length=2)


class LocationGeoQuery(BaseModel):
    latitude: float
    longitude: float


class LocationSearchRequest(BaseModel):
    criterion: Literal["ADDRESS", "GEO", "PHONE"] = "ADDRESS"
    address: LocationAddressQuery | None = None
    geo: LocationGeoQuery | None = None
    phone_number: str | None = None
    radius_miles: float = Field(default=25.0, ge=1.0, le=50.0)
    max_results: int = Field(default=10, ge=1, le=75)
    results_to_skip: int = Field(default=0, ge=0)


class FedExLocationHours(BaseModel):
    day_of_week: str
    operational_hours_type: str | None = None
    begin_time: str | None = None
    end_time: str | None = None


class FedExLocationItem(BaseModel):
    location_id: str | None = None
    display_name: str | None = None
    location_type: str | None = None
    distance_miles: float | None = None
    street_lines: list[str] = Field(default_factory=list)
    city: str | None = None
    state_or_province_code: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    phone_number: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    store_hours: list[FedExLocationHours] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)


class LocationSearchResponse(BaseModel):
    total_results: int = 0
    results_returned: int = 0
    matched_address: dict[str, Any] | None = None
    locations: list[FedExLocationItem] = Field(default_factory=list)
    source: str = "fedex_api"
    raw: dict[str, Any] | None = None
