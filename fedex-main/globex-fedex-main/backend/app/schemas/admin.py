from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.schemas.quota import UserQuotaStatus
from app.schemas.user import UserRead, UserSessionRead


class AdminNotificationItem(BaseModel):
    """Alerte in-app pour l’administrateur (pas d’email)."""

    id: str
    kind: str  # employee_pending | preference_pending
    reference_id: int
    user_name: str | None = None
    user_email: str | None = None
    risk_score: int | None = None
    created_at: datetime


class AdminNotificationsResponse(BaseModel):
    items: list[AdminNotificationItem]
    total: int


class AdminDashboardStats(BaseModel):
    total_users: int
    total_clients: int
    total_employees: int
    total_admins: int
    total_sessions: int
    total_messages: int
    total_tracking_requests: int
    pending_employees: int
    messages_last_7_days: int
    trackings_last_7_days: int
    new_users_last_7_days: int
    sessions_last_7_days: int
    logs_last_7_days: int
    total_events: int = 0
    events_today: int = 0
    pending_preference_submissions: int = 0
    email_configured: bool
    fedex_enabled: bool
    llm_enabled: bool


class ActivityLogRead(BaseModel):
    id: int
    user_id: int | None
    actor_user_id: int | None
    user_email: str | None = None
    user_name: str | None = None
    actor_email: str | None = None
    level: str
    category: str
    action: str
    message: str
    metadata_json: str
    ip_address: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogRead]
    total: int
    limit: int
    offset: int


class AdminUserListItem(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    status: str
    organization_id: str
    preferred_language: str
    created_at: datetime
    last_activity_at: datetime | None = None
    is_online: bool = False
    last_location: str | None = None
    messages_count: int = 0
    trackings_count: int = 0

    model_config = {"from_attributes": True}


class AdminUserDetail(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    status: str
    preferred_language: str
    response_preferences: str
    organization_id: str
    created_at: datetime
    sessions_count: int = 0
    messages_count: int = 0
    trackings_count: int = 0
    last_activity_at: datetime | None = None
    is_online: bool = False
    last_location: str | None = None
    recent_sessions: list[UserSessionRead] = []
    quotas: UserQuotaStatus | None = None

    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=20)
    preferred_language: str | None = Field(default=None, max_length=8)
    response_preferences: str | None = Field(default=None, max_length=4000)
    quota_messages_per_day: int | None = Field(default=None, ge=0, le=100_000)
    quota_trackings_per_day: int | None = Field(default=None, ge=0, le=100_000)
    quota_exports_per_day: int | None = Field(default=None, ge=0, le=100_000)


class AdminInviteUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    role: str = Field(default="employe", max_length=32)
    preferred_language: str = Field(default="fr", max_length=8)


class AdminInviteUserResponse(BaseModel):
    user: UserRead
    email_sent: bool
    message: str
