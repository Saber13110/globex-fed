from pydantic import BaseModel, Field


class TrackingEventSchema(BaseModel):
    at: str = ""
    description: str
    location: str = ""
    city: str = ""
    state_or_province: str = ""
    country: str = ""
    country_code: str = ""
    country_name: str = ""
    event_type: str = ""
    status_code: str = ""


class SpecialHandlingSchema(BaseModel):
    type: str = ""
    description: str = ""
    payment_type: str = ""


class AvailableImageSchema(BaseModel):
    type: str = ""
    size: str = ""
