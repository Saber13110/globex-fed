from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.client_agent import AgentQuestionnaire, AgentReasoning, AgentStep


class AiAssistantKpi(BaseModel):
    key: str
    label: str
    value: str
    trend_percent: float
    trend_up: bool
    icon: str


class AiInsightItem(BaseModel):
    id: str
    title: str
    description: str
    tone: str  # high | good | medium | info
    badge: str
    icon: str


class AiCapabilityItem(BaseModel):
    key: str
    title: str
    description: str
    icon: str


class AiServiceStatus(BaseModel):
    key: str
    name: str
    status: str
    operational: bool


class AiDataSource(BaseModel):
    key: str
    name: str
    connected: bool
    detail: str


class AiSuggestionItem(BaseModel):
    id: str
    text: str
    action: str


class AiConversationItem(BaseModel):
    id: int
    question: str
    created_at: datetime
    status: str  # completed | running | pending
    source: str  # admin | platform
    session_id: int | None = None


class AiAssistantOverview(BaseModel):
    kpis: list[AiAssistantKpi]
    insights: list[AiInsightItem]
    capabilities: list[AiCapabilityItem]
    system_status: list[AiServiceStatus]
    data_sources: list[AiDataSource]
    smart_suggestions: list[AiSuggestionItem]
    ask_examples: list[str]
    recent_conversations: list[AiConversationItem]
    quick_commands: list[str]


class CopilotHistoryMessage(BaseModel):
    role: str = Field(description="user | assistant")
    content: str = Field(max_length=4000)


class CopilotConversationStatePayload(BaseModel):
    last_module: str | None = None
    last_query_type: str | None = None
    last_tool_used: str | None = None
    last_items: list[dict[str, Any]] = Field(default_factory=list)
    last_payload: dict[str, Any] | None = None
    last_exportable_result: bool = False
    last_limit: int | None = None
    last_format: str | None = None


class AiAssistantQueryRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    quick_action: str | None = None
    agent_mode: bool = False
    conversation_history: list[CopilotHistoryMessage] = Field(default_factory=list)
    copilot_state: CopilotConversationStatePayload | dict[str, Any] | None = None
    image_base64: str | None = Field(default=None, max_length=5_600_000)
    image_mime_type: str | None = Field(default=None, max_length=64)
    attached_document_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_message_or_image(self) -> "AiAssistantQueryRequest":
        has_text = bool((self.message or "").strip())
        has_image = bool((self.image_base64 or "").strip())
        if not has_text and not has_image:
            raise ValueError("Message ou image requis.")
        return self


class AdminExportDownloadSpec(BaseModel):
    preset: str = "admin_logs"
    hours: int | None = 2
    limit: int | None = None
    module: str | None = None
    tracking_numbers: str | None = None
    filename: str = "activity-logs.pdf"
    format: str | None = "pdf"
    export_token: str | None = None
    records: int | None = None


class ExportPreviewPayload(BaseModel):
    intent_id: str
    module: str
    format: str
    records: int
    period: str
    estimated_size_kb: int
    filename: str
    hours: int = 24
    limit: int = 50
    period_type: str | None = None


class ExportExecuteRequest(BaseModel):
    suggested_action: dict[str, Any] = Field(description="Action export confirmée par l'admin")


class ExportExecuteResponse(BaseModel):
    success: bool
    file_name: str | None = None
    download_url: str | None = None
    records: int = 0
    export_download: AdminExportDownloadSpec | None = None
    export_status: str = "completed"
    error: str | None = None
    reply: str | None = None


class AiAssistantQueryResponse(BaseModel):
    reply: str
    intent: str | None = None
    conversation_id: int | None = None
    agent_type: str | None = None
    agent_type_label: str | None = None
    mission_id: int | None = None
    action_executed: bool = False
    needs_approval: bool = False
    approval_id: int | None = None
    analysis_only: bool = False
    agent_steps: list[AgentStep] = Field(default_factory=list)
    agent_reasoning: AgentReasoning | None = None
    export_download: AdminExportDownloadSpec | None = None
    agent_questionnaire: AgentQuestionnaire | None = None
    llm_degraded: bool = False
    llm_provider: str | None = None
    gpt_slug: str | None = None
    knowledge_hits: int = 0
    tools_used: list[str] = Field(default_factory=list)
    copilot_state: dict[str, Any] | None = None
    # Champs enrichis (alias / traçabilité)
    answer: str | None = None
    mode: str | None = Field(
        default=None,
        description="gemini | ollama | local_fallback",
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning_summary: str | None = None
    error: str | None = None
    language: str | None = Field(default=None, description="fr | en | es | ar | de")
    execution_time_ms: float | None = None
    sources_used: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    suggested_action: dict[str, Any] | None = None
    export_preview: ExportPreviewPayload | dict[str, Any] | None = None
    export_status: str | None = Field(
        default=None,
        description="pending | in_progress | completed | error",
    )
    export_result: dict[str, Any] | None = None
    verified_data: str | None = None
