from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.tracking_event import AvailableImageSchema, SpecialHandlingSchema, TrackingEventSchema
from app.schemas.visibility import PodInfoSchema, VisibilityEventSchema


class TrackingResponse(BaseModel):
    tracking_number: str
    status: str | None = None
    status_code: str | None = None
    status_description: str | None = None
    current_location: str | None = None
    city: str | None = None
    state_or_province: str | None = None
    country: str | None = None
    estimated_delivery: str | None = None
    actual_delivery: str | None = None
    events: list[TrackingEventSchema] = []
    visibility_events: list[VisibilityEventSchema] = Field(default_factory=list)
    service_type: str | None = None
    service_description: str | None = None
    shipper: str | None = None
    recipient: str | None = None
    origin_location: str | None = None
    destination_location: str | None = None
    weight: str | None = None
    dimensions: str | None = None
    package_type: str | None = None
    package_count: str | None = None
    special_handlings: list[SpecialHandlingSchema] = Field(default_factory=list)
    delivery_details: dict[str, Any] | None = None
    received_by_name: str | None = None
    available_images: list[AvailableImageSchema] = Field(default_factory=list)
    available_notifications: list[str] = Field(default_factory=list)
    hold_at_location: dict[str, Any] | None = None
    service_commit_message: str | None = None
    pod_available: bool = False
    pod_info: PodInfoSchema | None = None
    source: str | None = None
    details: dict[str, Any]


class HistoryItem(BaseModel):
    id: int
    session_id: int | None = None
    tracking_number: str
    user_question: str
    bot_response: str
    status: str | None
    current_location: str | None
    estimated_delivery: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
