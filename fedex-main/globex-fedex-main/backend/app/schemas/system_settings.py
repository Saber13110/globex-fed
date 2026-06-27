from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class NotificationSettings(BaseModel):
    email: bool = True
    sms: bool = False
    in_app: bool = True
    critical_alerts: bool = True


class SecuritySettings(BaseModel):
    mfa_enabled: bool = True


class SmtpIntegrationSettings(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    use_tls: bool = True
    password_set: bool = False


class IntegrationSettings(BaseModel):
    smtp: SmtpIntegrationSettings = Field(default_factory=SmtpIntegrationSettings)


class AiSettings(BaseModel):
    provider: Literal["gemini", "openai", "claude", "ollama"] = "gemini"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=256, le=32768)
    system_prompt: str = ""


class SystemSettingsPayload(BaseModel):
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    ai: AiSettings = Field(default_factory=AiSettings)


class SystemSettingsRead(SystemSettingsPayload):
    updated_at: datetime | None = None


class SystemSettingsPatch(BaseModel):
    notifications: NotificationSettings | None = None
    security: SecuritySettings | None = None
    integrations: IntegrationSettings | None = None
    ai: AiSettings | None = None


class ServiceHealthItem(BaseModel):
    key: str
    label: str
    status: Literal["online", "offline", "degraded", "disabled", "not_configured"]
    availability_percent: float
    latency_ms: float | None = None
    last_check: datetime
    detail: str = ""


class SystemHealthResponse(BaseModel):
    services: list[ServiceHealthItem]


class SystemInfoResponse(BaseModel):
    version: str
    environment: str
    database_status: str
    server: str
    last_updated: datetime


class SystemOperationResponse(BaseModel):
    ok: bool
    message: str
    detail: dict[str, Any] | None = None


class TestEmailRequest(BaseModel):
    to: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


class IntegrationTestResponse(BaseModel):
    ok: bool
    provider: str
    message: str
    latency_ms: float | None = None
