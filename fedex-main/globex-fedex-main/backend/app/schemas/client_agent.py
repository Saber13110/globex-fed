from pydantic import BaseModel, Field


class AgentQuestionOption(BaseModel):
    id: str
    label: str
    description: str | None = None


class AgentQuestion(BaseModel):
    id: str
    label: str
    hint: str | None = None
    question_type: str = "single_choice"
    options: list[AgentQuestionOption] = Field(default_factory=list)
    required: bool = True


class AgentQuestionnaire(BaseModel):
    flow_id: str
    task_type: str
    task_label: str
    intro: str
    questions: list[AgentQuestion] = Field(default_factory=list)
    allow_multiple_submit: bool = True


class AgentStep(BaseModel):
    label: str
    status: str
    detail: str | None = None


class AgentReasoning(BaseModel):
    """Raisonnement interne de l'agent (OBJECTIF → PLAN → ACTION → VÉRIFICATION)."""

    objective: str = ""
    plan: list[str] = Field(default_factory=list)
    action_tool: str = ""
    action_label: str = ""
    verification: str = ""
    verified: bool | None = None
    verification_note: str = ""


class AgentAnswersSubmit(BaseModel):
    flow_id: str
    answers: dict[str, str] = Field(default_factory=dict)


class AgentSuggestion(BaseModel):
    task_type: str
    label: str
    message: str
    prefill: str
