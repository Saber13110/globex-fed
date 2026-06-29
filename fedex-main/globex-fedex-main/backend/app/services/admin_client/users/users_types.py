"""Types partagés agent Utilisateurs admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class UsersTaskType(str, Enum):
    user_list = "user_list"
    user_detail = "user_detail"
    user_logs = "user_logs"
    user_permissions = "user_permissions"
    user_suspend = "user_suspend"
    user_reactivate = "user_reactivate"
    user_delete = "user_delete"
    user_update_name = "user_update_name"
    user_reset_password = "user_reset_password"
    ambiguous = "ambiguous"


class UsersProfile(str, Enum):
    LIST = "list"
    DETAIL = "detail"
    LOGS = "logs"
    PERMISSIONS = "permissions"
    CONFIRM = "confirm"
    DONE = "done"
    ERROR = "error"
    CLARIFY = "clarify"


class UsersToolError(Exception):
    """Échec outil utilisateurs admin."""


@dataclass
class UsersPlan:
    task_type: UsersTaskType
    user_id: int | None = None
    role_filter: str | None = None
    status_filter: str | None = None
    search_query: str | None = None
    new_name: str | None = None
    suspend_reason: str = ""
    notify_email: bool = False
    limit: int = 15
    sort_by: str | None = None  # last_activity | created_at | online
    list_variant: str | None = None  # activity | ever_suspended
    want_pdf: bool = False
    profile: UsersProfile = UsersProfile.LIST
    raw_matches: list[str] = field(default_factory=list)
    needs_router: bool = False
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_candidates: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PendingUserAction:
    action: str
    user_id: int
    payload: dict[str, str] = field(default_factory=dict)
