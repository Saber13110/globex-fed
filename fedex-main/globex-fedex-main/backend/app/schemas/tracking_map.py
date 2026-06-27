"""Schémas pour la carte de suivi FedEx."""

from pydantic import BaseModel, Field


class TrackingMapPointSchema(BaseModel):
    step: int = 0
    date: str = ""
    eventDescription: str = ""
    city: str = ""
    stateOrProvinceCode: str = ""
    countryCode: str = ""
    countryName: str = ""
    latitude: float | None = None
    longitude: float | None = None
    kind: str = "transit"
    label: str = ""


class TrackingMapPayloadSchema(BaseModel):
    trackingNumber: str
    status: str | None = None
    currentLocation: str | None = None
    events: list[dict] = Field(default_factory=list)
    mapPoints: list[TrackingMapPointSchema] = Field(default_factory=list)
    map_available: bool = False
    show_tracking_map: bool = False
    delivered: bool = False
