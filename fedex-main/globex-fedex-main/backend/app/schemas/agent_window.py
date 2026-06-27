from datetime import datetime

from pydantic import BaseModel, Field


class AgentWindowHistoryMessage(BaseModel):
    role: str = Field(description="user | assistant")
    content: str = Field(max_length=4000)


class AgentWindowChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, description="ID session FedEx (UUID)")
    conversation_history: list[AgentWindowHistoryMessage] = Field(default_factory=list)


class AgentWindowChatResponse(BaseModel):
    reply: str
    session_id: str
    jarvis_session_id: str | None = None
    engine: str = "jarvis"
    latency_ms: float | None = None
    redirect_to_copilot: bool = False
    copilot_hint: str | None = None


class AgentWindowSessionRead(BaseModel):
    id: str
    title: str
    jarvis_session_id: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class AgentWindowSessionListResponse(BaseModel):
    sessions: list[AgentWindowSessionRead]


class AgentWindowMessageRead(BaseModel):
    id: int
    sender: str
    message_text: str
    created_at: datetime
    latency_ms: float | None = None


class AgentWindowSessionDetail(BaseModel):
    session: AgentWindowSessionRead
    messages: list[AgentWindowMessageRead]


class AgentWindowHealthResponse(BaseModel):
    enabled: bool
    online: bool
    jarvis_base_url: str
    detail: str | None = None
    latency_ms: float | None = None
