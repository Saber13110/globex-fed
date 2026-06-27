from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FaqItem(BaseModel):
    id: str
    question: str
    answer: str


class FaqListResponse(BaseModel):
    items: list[FaqItem]
    language: str


TicketCategory = Literal["tracking", "documents", "ai", "security", "account", "other"]
TicketPriority = Literal["low", "medium", "high"]
TicketStatus = Literal["open", "pending", "resolved", "closed"]


class SupportTicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    category: TicketCategory = "other"
    priority: TicketPriority = "medium"
    message: str = Field(..., min_length=10, max_length=4000)
    attachmentUrl: str | None = Field(default=None, max_length=512)

    @field_validator("subject", "message")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @field_validator("attachmentUrl")
    @classmethod
    def normalize_attachment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SupportTicketCreatedResponse(BaseModel):
    success: bool = True
    ticketId: str
    id: int
    status: str
    createdAt: datetime


class SupportTicketStatusUpdate(BaseModel):
    status: TicketStatus


class SupportMessageCreate(BaseModel):
    message: str = Field(default="", max_length=4000)
    attachmentUrl: str | None = Field(default=None, max_length=512)


class SupportTicketMessageRead(BaseModel):
    id: int
    author_role: str
    body: str
    attachment_url: str | None = None
    created_at: datetime
    author_name: str | None = None

    model_config = {"from_attributes": True}


class SupportTicketRead(BaseModel):
    id: int
    ticket_number: str | None = None
    subject: str
    message: str
    category: str = "other"
    priority: str = "medium"
    status: str
    attachment_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    unread_admin: bool = False

    model_config = {"from_attributes": True}


class SupportTicketDetailRead(SupportTicketRead):
    messages: list[SupportTicketMessageRead] = []


class SupportTicketAdminDetailRead(SupportTicketDetailRead):
    user_name: str | None = None
    user_email: str | None = None


class SupportTicketListResponse(BaseModel):
    items: list[SupportTicketRead]


class ClientNotificationRead(BaseModel):
    id: int
    kind: str
    type: str | None = None
    title: str
    message: str
    link: str
    reference_id: int | None
    related_ticket_id: int | None = None
    related_tracking_number: str = ""
    priority: str = "medium"
    sender_id: int | None = None
    sender_role: str | None = None
    status: str = "unread"
    is_read: bool
    created_at: datetime
    read_at: datetime | None = None

    model_config = {"from_attributes": True}


class ClientNotificationListResponse(BaseModel):
    items: list[ClientNotificationRead]
    unread_count: int
