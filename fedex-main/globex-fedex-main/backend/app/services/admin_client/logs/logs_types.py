"""Types partagés agent Logs admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LogsTaskType(str, Enum):
    log_list = "log_list"
    log_search = "log_search"
    log_detail = "log_detail"
    log_summary_user_day = "log_summary_user_day"
    log_summary_platform_day = "log_summary_platform_day"
    log_anomalies = "log_anomalies"
    log_open_conversation = "log_open_conversation"
    log_suspend_user = "log_suspend_user"
    ambiguous = "ambiguous"


class LogsProfile(str, Enum):
    LIST = "list"
    DETAIL = "detail"
    SUMMARY = "summary"
    ANOMALIES = "anomalies"
    CONVERSATION = "conversation"
    CLARIFY = "clarify"
    CONFIRM = "confirm"
    DONE = "done"
    ERROR = "error"


class LogsToolError(Exception):
    """Échec outil logs admin."""


@dataclass
class PendingLogAction:
    action: str
    log_id: int | None = None
    user_id: int | None = None
    payload: dict[str, str] = field(default_factory=dict)


@dataclass
class LogsPlan:
    task_type: LogsTaskType
    log_id: int | None = None
    user_id: int | None = None
    user_query: str | None = None
    level_filter: str | None = None
    category_filter: str | None = None
    action_filter: str | None = None
    search_query: str | None = None
    period_hours: int | None = None
    since_today: bool = False
    limit: int = 30
    want_pdf: bool = False
    want_excel: bool = False
    profile: LogsProfile = LogsProfile.LIST
    raw_matches: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_candidates: list[dict[str, str]] = field(default_factory=list)
