from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.preference_profile import PreferenceProfileStructured


class PreferenceSubmitRequest(BaseModel):
    """Soumission structurée (recommandé) ou texte libre legacy."""

    proposed_text: str | None = Field(default=None, max_length=4000)
    tone: str | None = Field(default=None, max_length=32)
    cite_fedex: bool | None = None
    short_answers: bool | None = None
    free_notes: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def require_content(self) -> "PreferenceSubmitRequest":
        has_structured = self.tone is not None or self.cite_fedex is not None or self.short_answers is not None
        has_notes = bool((self.free_notes or "").strip())
        has_legacy = bool((self.proposed_text or "").strip())
        if not has_structured and not has_notes and not has_legacy:
            raise ValueError("Précisez au moins le ton ou une note.")
        return self


class PreferenceSubmissionRead(BaseModel):
    id: int
    user_id: int
    user_email: str | None = None
    user_name: str | None = None
    proposed_text: str
    structured: PreferenceProfileStructured | None = None
    status: str
    risk_score: int
    risk_reasons: list[str]
    rejection_note: str
    created_at: datetime
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserPreferencesState(BaseModel):
    active: str
    active_structured: PreferenceProfileStructured | None = None
    pending: str | None = None
    pending_structured: PreferenceProfileStructured | None = None
    pending_id: int | None = None
    pending_status: str | None = None
    pending_risk_score: int | None = None
    pending_risk_reasons: list[str] = Field(default_factory=list)
    rejection_note: str | None = None
    submitted_at: datetime | None = None


class PreferenceRejectRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)
