from datetime import datetime

from pydantic import BaseModel, Field


class UserNotificationRead(BaseModel):
    id: int
    user_id: int
    sender_id: int | None = None
    sender_role: str | None = None
    type: str
    title: str
    message: str
    status: str
    priority: str = "medium"
    related_ticket_id: int | None = None
    related_tracking_number: str = ""
    link: str = "/notifications"
    is_read: bool = False
    created_at: datetime
    read_at: datetime | None = None


class UserNotificationListResponse(BaseModel):
    items: list[UserNotificationRead]
    unread_count: int
    total: int = 0


class UserNotificationFilter(BaseModel):
    type: str | None = None
    status: str | None = None
    q: str | None = Field(default=None, max_length=120)
