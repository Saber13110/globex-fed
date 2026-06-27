from datetime import datetime

from pydantic import BaseModel, Field


class NotificationKpiItem(BaseModel):
    key: str
    label: str
    value: int
    trend_value: float
    trend_up: bool
    trend_label: str
    icon: str
    sparkline: list[float]


class NotificationItem(BaseModel):
    id: int
    category: str
    title: str
    message: str
    tracking_number: str
    route: str
    priority: str
    channel: str
    icon: str
    action_label: str
    action_type: str
    action_ref: str
    is_read: bool
    is_archived: bool
    created_at: datetime
    time_label: str


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int
    page: int
    page_size: int
    unread_count: int


class NotificationStatsResponse(BaseModel):
    kpis: list[NotificationKpiItem]
    unread_count: int


class NotificationPreferences(BaseModel):
    web_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    ai_reports: bool = True
    incidents: bool = True


class NotificationPreferencesUpdate(BaseModel):
    web_enabled: bool | None = None
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    ai_reports: bool | None = None
    incidents: bool | None = None


class AiNotificationInsight(BaseModel):
    id: str
    text: str
    tone: str


class TimelineEvent(BaseModel):
    id: str
    time_label: str
    title: str
    subtitle: str
    icon: str
    tone: str
    created_at: datetime


class NotificationOverview(BaseModel):
    stats: NotificationStatsResponse
    ai_insights: list[AiNotificationInsight]
    timeline: list[TimelineEvent]


class TestAlertRequest(BaseModel):
    title: str = Field(default="Test Alert", max_length=200)
    message: str = Field(default="Custom alert test from Notification Center", max_length=500)


class CreateRuleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="system")
    channel: str = Field(default="web")


class WebhookImportResponse(BaseModel):
    imported: int
    message: str


class AiReportNotificationResponse(BaseModel):
    reply: str
    report_id: int | None = None
