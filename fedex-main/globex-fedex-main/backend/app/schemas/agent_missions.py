"""Schémas API — Agent Missions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentType = Literal["logs", "support", "users", "tracking", "notifications", "summary"]
ScheduleType = Literal["now", "datetime", "daily", "weekly"]
MissionStatus = Literal[
    "draft",
    "waiting_plan_approval",
    "scheduled",
    "running",
    "waiting_permission",
    "completed",
    "failed",
    "cancelled",
]


class AgentMissionCreate(BaseModel):
    agent_type: AgentType
    task_description: str = Field(min_length=10, max_length=4000)
    schedule_type: ScheduleType = "now"
    scheduled_at: datetime | None = None
    schedule_time: str = "08:00"
    max_items: int = Field(default=10, ge=1, le=500)
    max_duration_minutes: int = Field(default=15, ge=1, le=120)
    require_approval_sensitive: bool = True
    notify_on_start: bool = True
    notify_on_complete: bool = True
    plan_json: str | None = None


class AgentMissionWorkflowUpdate(BaseModel):
    agent_type: AgentType
    task_description: str = Field(min_length=10, max_length=4000)
    schedule_type: ScheduleType = "now"
    scheduled_at: datetime | None = None
    schedule_time: str = "08:00"
    max_items: int = Field(default=10, ge=1, le=500)
    max_duration_minutes: int = Field(default=15, ge=1, le=120)
    require_approval_sensitive: bool = True
    notify_on_start: bool = True
    notify_on_complete: bool = True
    plan_json: str = Field(min_length=2)


class AgentMissionStepRead(BaseModel):
    id: int
    step_order: int
    title: str
    description: str
    action_type: str
    is_sensitive: bool
    status: str
    output_json: str
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class AgentApprovalRead(BaseModel):
    id: int
    mission_id: int
    step_id: int
    action_type: str
    description: str
    payload_json: str
    status: str
    resolved_by_admin_id: int | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentExecutionLogRead(BaseModel):
    id: int
    mission_id: int
    step_id: int | None
    level: str
    message: str
    details_json: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentMissionMessageRead(BaseModel):
    id: int
    mission_id: int
    sender: str
    content: str
    metadata_json: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentMissionRead(BaseModel):
    id: int
    admin_id: int
    agent_type: str
    task_description: str
    status: str
    schedule_type: str
    scheduled_at: datetime | None
    schedule_time: str
    max_items: int
    max_duration_minutes: int
    require_approval_sensitive: bool
    notify_on_start: bool = True
    notify_on_complete: bool = True
    plan_json: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    steps: list[AgentMissionStepRead] = []
    pending_approvals: list[AgentApprovalRead] = []

    model_config = {"from_attributes": True}


class AgentStepResultRead(BaseModel):
    step_id: int
    step_order: int
    title: str
    action_type: str
    status: str
    output: dict[str, Any]


class AgentMissionResults(BaseModel):
    has_results: bool
    executive_summary: str
    metrics: dict[str, Any]
    step_results: list[AgentStepResultRead]


class AgentMissionListItem(BaseModel):
    id: int
    agent_type: str
    task_description: str
    status: str
    schedule_type: str
    scheduled_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    has_results: bool = False
    result_preview: str = ""

    model_config = {"from_attributes": True}


class AgentMissionListResponse(BaseModel):
    items: list[AgentMissionListItem]
    total: int
    stats: dict[str, int]


class AgentMissionDetailResponse(AgentMissionRead):
    logs: list[AgentExecutionLogRead] = []
    messages: list[AgentMissionMessageRead] = []
    agent_steps: list[dict[str, Any]] = []
    agent_reasoning: dict[str, Any] | None = None
    results: AgentMissionResults


class AgentApprovalActionResponse(BaseModel):
    approval: AgentApprovalRead
    mission: AgentMissionRead
