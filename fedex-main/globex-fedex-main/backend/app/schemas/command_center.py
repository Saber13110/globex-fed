from datetime import datetime

from pydantic import BaseModel, Field


class KpiTrendPoint(BaseModel):
    label: str
    value: float


class KpiCardData(BaseModel):
    title: str
    value: int
    trend_percent: float
    trend_up: bool
    sparkline: list[float]
    icon: str = "package"
    display_value: str | None = None
    suffix: str = ""


class HeroStatItem(BaseModel):
    label: str
    value: int
    icon: str


class LiveShipmentItem(BaseModel):
    id: int
    route: str
    origin: str
    destination: str
    origin_flag: str
    destination_flag: str
    carrier: str
    tracking_number: str
    status: str
    status_key: str
    eta_label: str
    progress_percent: int
    updated_at: datetime


class OverviewMetric(BaseModel):
    label: str
    value: str
    trend_percent: float
    trend_up: bool
    icon: str


class ExecutiveInsight(BaseModel):
    id: str
    tone: str  # purple | orange | green | blue
    message: str
    icon: str


class RecentUserItem(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    created_at: datetime


class RecentConversationItem(BaseModel):
    id: int
    session_id: int
    title: str
    preview: str
    user_name: str | None
    priority: str  # low | medium | high
    created_at: datetime


class SystemHealthItem(BaseModel):
    name: str
    key: str
    status: str
    percent: float
    operational: bool


class UserRoleSlice(BaseModel):
    label: str
    role_key: str
    count: int
    color: str


class FedexApiMetrics(BaseModel):
    requests_today: int
    success_rate: float
    latency_ms: int
    error_rate: float
    requests_series: list[KpiTrendPoint]


class ActivityTimelineItem(BaseModel):
    time_label: str
    message: str
    category: str
    level: str
    created_at: datetime


class CommandCenterPayload(BaseModel):
    hero_stats: list[HeroStatItem]
    today_overview: list[OverviewMetric]
    executive_insights: list[ExecutiveInsight]
    kpis: list[KpiCardData]
    live_shipments: list[LiveShipmentItem]
    recent_conversations: list[RecentConversationItem]
    system_health: list[SystemHealthItem]
    user_roles: list[UserRoleSlice]
    pending_invitations: int
    recent_users: list[RecentUserItem]
    fedex_metrics: FedexApiMetrics
    activity_timeline: list[ActivityTimelineItem]
    open_incidents: int
    notification_count: int
    total_users: int
    online_users: int = 0
    generated_at: datetime | None = None


class CommandCenterAiRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    quick_action: str | None = None


class CommandCenterAiResponse(BaseModel):
    reply: str
    intent: str | None = None
