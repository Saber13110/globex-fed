"""Types partagés agent e-mail admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EmailTaskType(str, Enum):
    send_user_email = "send_user_email"
    ambiguous = "ambiguous"


class EmailProfile(str, Enum):
    DRAFT = "draft"
    CLARIFY = "clarify"
    CONFIRM = "confirm"
    DONE = "done"
    ERROR = "error"


class EmailScenario(str, Enum):
    custom = "custom"
    user_suspend = "user_suspend"
    user_reactivate = "user_reactivate"
    ticket_reply = "ticket_reply"
    ticket_resolved = "ticket_resolved"


class EmailToolError(Exception):
    """Échec outil e-mail admin."""


@dataclass
class EmailPlan:
    task_type: EmailTaskType
    user_id: int | None = None
    recipient_email: str | None = None
    admin_note: str = ""
    subject_hint: str = ""
    scenario: EmailScenario = EmailScenario.custom
    profile: EmailProfile = EmailProfile.DRAFT
    attachment_export_token: str | None = None
    raw_matches: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""


@dataclass
class AdminEmailDraft:
    to: str
    subject: str
    body_text: str
    user_id: int | None = None
    attachment_bytes: bytes | None = None
    attachment_filename: str | None = None
    attachment_mime: str = "application/pdf"


@dataclass
class PendingEmailAction:
    to: str
    subject: str
    body_text: str
    user_id: int | None = None
    attachment_export_token: str | None = None
