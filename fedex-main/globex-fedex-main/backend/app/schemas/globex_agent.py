"""Schémas API Globex Agent — remplace le pipeline copilot."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.chat import ShipmentSummary


class GlobexAgentHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GlobexAgentChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    agent_mode: bool = False
    conversation_history: list[GlobexAgentHistoryMessage] = Field(default_factory=list)
    ui_language: str = "fr"
    # Pipeline admin_client : session miroir + pièce jointe (image / PDF / Excel).
    chat_session_id: int | None = None
    image_base64: str | None = None
    image_mime_type: str | None = None
    file_name: str | None = None


class GlobexAgentStep(BaseModel):
    label: str
    status: str
    detail: str | None = None


class GlobexAgentChatResponse(BaseModel):
    reply: str
    mode: str = "jarvis"
    tools_used: list[str] = Field(default_factory=list)
    agent_steps: list[GlobexAgentStep] = Field(default_factory=list)
    needs_approval: bool = False
    approval_id: int | None = None
    approval_hint: str | None = None
    mission_id: int | None = None
    action_executed: bool = False
    export_download: dict[str, Any] | None = None
    llm_degraded: bool = False
    intent: str | None = None
    execution_time_ms: float | None = None
    shipment: ShipmentSummary | None = None
    chat_session_id: int | None = None


class GlobexAgentToolExecuteRequest(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    agent_mode: bool = True


class GlobexAgentToolExecuteResponse(BaseModel):
    tool: str
    success: bool
    response: dict[str, Any] = Field(default_factory=dict)
    needs_approval: bool = False


class GlobexAgentToolInfo(BaseModel):
    name: str
    description: str
    sensitivity: str
    requires_approval: bool


class GlobexAgentToolsResponse(BaseModel):
    tools: list[GlobexAgentToolInfo]


class GlobexAgentCatalogItem(BaseModel):
    name: str
    description: str
    sensitivity: str
    requires_approval: bool
    is_read_tool: bool
    approval_mode: str
    phase: str
    group: str
    has_handler: bool


class GlobexAgentCatalogResponse(BaseModel):
    target_count: int = 62
    registered_count: int
    complete: bool
    tools: list[GlobexAgentCatalogItem]
    groups: dict[str, int] = Field(default_factory=dict)
    phases: dict[str, int] = Field(default_factory=dict)
    missing_handlers: list[str] = Field(default_factory=list)


class GlobexAgentHealthResponse(BaseModel):
    enabled: bool
    ollama_model: str
    ollama_online: bool
    detail: str | None = None
    kernel_version: str = "unknown"
    simple_mode: bool = False
    proactive: dict[str, Any] = Field(default_factory=dict)


class GlobexAgentApproveResponse(BaseModel):
    approval_id: int
    status: str
    reply: str | None = None
    mission_id: int | None = None
