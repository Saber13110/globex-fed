from datetime import datetime

from pydantic import BaseModel


class AdminConversationKpi(BaseModel):
    label: str
    value: int
    trend_percent: float
    trend_up: bool
    icon: str


class AdminConversationListItem(BaseModel):
    id: int
    session_id: int
    title: str
    preview: str
    user_id: int
    user_name: str
    user_email: str = ""
    user_status: str = "active"
    user_initial: str
    category: str
    status: str
    status_key: str
    priority: str
    is_unread: bool
    updated_label: str
    created_at: datetime


class AdminConversationsPage(BaseModel):
    kpis: list[AdminConversationKpi]
    conversations: list[AdminConversationListItem]


class AdminConversationMessage(BaseModel):
    id: int
    sender: str
    message_text: str
    created_at: datetime
    time_label: str


class AdminConversationAnalytics(BaseModel):
    response_time: str
    response_time_trend: float
    resolution_time: str
    resolution_time_trend: float
    satisfaction: str
    satisfaction_trend: float
    messages: int
    interactions: int


class AdminConversationDetail(BaseModel):
    id: int
    session_id: int
    title: str
    user_id: int
    user_name: str
    user_email: str = ""
    user_status: str = "active"
    user_initial: str
    category: str
    status: str
    status_key: str
    priority: str
    channel: str
    created_at: datetime
    created_label: str
    updated_label: str
    is_unread: bool
    tags: list[str]
    messages: list[AdminConversationMessage]
    analytics: AdminConversationAnalytics
