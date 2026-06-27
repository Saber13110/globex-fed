"""Schémas API sécurité / IDS."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SecurityIncidentRead(BaseModel):
    id: int
    user_id: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    user_status: str | None = None
    ip_address: str = ""
    source: str
    threat_type: str
    severity: str
    score: int
    status: str
    title: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str
    auto_eligible: bool
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_note: str = ""


class SecurityIncidentListResponse(BaseModel):
    items: list[SecurityIncidentRead]
    total: int
    open_count: int


class SecurityIncidentResolveRequest(BaseModel):
    status: str = Field(..., pattern="^(acknowledged|resolved|false_positive)$")
    note: str | None = Field(default=None, max_length=2000)


class SecurityPolicyRule(BaseModel):
    trigger: str
    threshold: int = 1
    action: str = "alert_only"


class SecurityPolicyRead(BaseModel):
    auto_mode_enabled: bool
    ai_ids_enabled: bool
    rules: list[SecurityPolicyRule]
    enabled_by_admin_id: int | None = None
    enabled_at: datetime | None = None
    updated_at: datetime | None = None


class SecurityPolicyUpdateRequest(BaseModel):
    auto_mode_enabled: bool | None = None
    ai_ids_enabled: bool | None = None
    rules: list[SecurityPolicyRule] | None = None


class SecurityAgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class SecurityAgentResponse(BaseModel):
    reply: str
    actions_taken: list[str] = Field(default_factory=list)
    auto_mode_enabled: bool = False
