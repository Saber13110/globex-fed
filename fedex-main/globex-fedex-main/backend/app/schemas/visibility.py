from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class VisibilityEventSchema(BaseModel):
    id: int | None = None
    tracking_number: str
    event_type: str
    event_type_label: str | None = None
    event_code: str | None = None
    description: str
    location: str | None = None
    occurred_at: str | None = None
    source: str | None = None
    created_at: str | None = None


class PodInfoSchema(BaseModel):
    tracking_number: str
    status: str | None = None
    delivered_at: str | None = None
    delivered_time: str | None = None
    delivery_address: str | None = None
    received_by_name: str | None = None
    signature_available: bool = False
    carrier_service: str | None = None
    current_location: str | None = None
    source: str | None = None


class WebhookIngestResponse(BaseModel):
    accepted: int
    tracking_numbers: list[str] = Field(default_factory=list)
    message: str


class VisibilityEventsResponse(BaseModel):
    tracking_number: str
    events: list[VisibilityEventSchema]
    count: int
