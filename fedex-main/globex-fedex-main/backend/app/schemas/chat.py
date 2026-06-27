from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.tracking_event import TrackingEventSchema
from app.schemas.tracking_map import TrackingMapPointSchema
from app.schemas.visibility import PodInfoSchema, VisibilityEventSchema
from app.schemas.client_agent import AgentQuestionnaire, AgentReasoning, AgentStep, AgentSuggestion


class ChatMessageRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    session_id: int | None = None
    response_preferences: str | None = Field(default=None, max_length=1200)
    preferred_name: str | None = Field(default=None, max_length=120)
    ui_language: str | None = Field(default=None, max_length=16)
    image_base64: str | None = Field(default=None, max_length=5_600_000)
    image_mime_type: str | None = Field(default=None, max_length=64)
    agent_mode: bool = False
    agent_flow_id: str | None = Field(default=None, max_length=36)
    agent_answers: dict[str, str] | None = None

    @model_validator(mode="after")
    def require_text_or_image(self) -> "ChatMessageRequest":
        has_text = bool(self.message and self.message.strip())
        has_image = bool(self.image_base64 and self.image_base64.strip())
        has_agent_answers = bool(self.agent_flow_id and self.agent_answers)
        if not has_text and not has_image and not has_agent_answers:
            raise ValueError("Message ou image requis.")
        return self


class ShipmentSummary(BaseModel):
    tracking_number: str
    status: str | None = None
    current_location: str | None = None
    estimated_delivery: str | None = None
    events: list[TrackingEventSchema] = Field(default_factory=list)
    visibility_events: list[VisibilityEventSchema] = Field(default_factory=list)
    weight: str | None = None
    dimensions: str | None = None
    pod_available: bool = False
    pod_info: PodInfoSchema | None = None
    map_points: list[TrackingMapPointSchema] = Field(default_factory=list)
    map_available: bool = False
    show_tracking_map: bool = False
    show_timeline: bool = False
    timeline_total: int = 0
    delivered: bool = False
    raw: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class ChatAiRequest(BaseModel):
    """Requête pour le endpoint IA (test / intégration) sans persistance obligatoire."""

    message: str = Field(..., min_length=1, max_length=4000)
    ui_language: str | None = Field(default=None, max_length=16)
    response_preferences: str | None = Field(default=None, max_length=1200)
    preferred_name: str | None = Field(default=None, max_length=120)


class ChatAiResponse(BaseModel):
    reply: str
    intent: str
    tracking_number: str | None = None
    llm_provider: str
    fedex_data_available: bool = False


class ExportDownloadSpec(BaseModel):
    session_id: int = 0
    tracking_numbers: list[str] = Field(default_factory=list)
    preset: str = "tracking"
    include_events: bool = True
    export_token: str | None = None
    filename: str | None = None
    format: str | None = None


class ChatMessageResponse(BaseModel):
    reply: str
    session_id: int
    session_title: str | None = None
    source: str
    shipment: ShipmentSummary | None = None
    intent: str | None = None
    tracking_number: str | None = None
    llm_provider: str | None = None
    export_download: ExportDownloadSpec | None = None
    agent_mode: bool = False
    agent_phase: str | None = None
    agent_questionnaire: AgentQuestionnaire | None = None
    agent_steps: list[AgentStep] = Field(default_factory=list)
    agent_reasoning: AgentReasoning | None = None
    agent_suggestion: AgentSuggestion | None = None
    tools_used: list[str] = Field(default_factory=list)
    gpt_slug: str | None = None
    knowledge_hits: int = 0


class ChatSessionRead(BaseModel):
    id: int
    title: str
    collection_id: int | None
    tags: str
    is_pinned: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionMessageRead(BaseModel):
    id: int
    sender: str
    source: str
    message_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    collection_id: int | None = None
    tags: str | None = Field(default=None, max_length=800)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class ChatCollectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ChatCollectionRead(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ShareConversationCreateRequest(BaseModel):
    include_tracking_details: bool = False


class ShareConversationRead(BaseModel):
    share_token: str
    include_tracking_details: bool


class SharedConversationPreview(BaseModel):
    session_id: int
    title: str
    include_tracking_details: bool
    messages: list[ChatSessionMessageRead]


class ImportSharedConversationResponse(BaseModel):
    session_id: int
