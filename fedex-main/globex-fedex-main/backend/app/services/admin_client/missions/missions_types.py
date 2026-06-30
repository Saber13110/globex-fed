"""Types partagés — Mission Control admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MissionsTaskType(str, Enum):
    mission_list = "mission_list"
    mission_results = "mission_results"
    mission_logs_summary = "mission_logs_summary"
    mission_retry = "mission_retry"
    mission_resume = "mission_resume"
    mission_cancel = "mission_cancel"
    mission_delete = "mission_delete"
    ambiguous = "ambiguous"


class MissionsProfile(str, Enum):
    LIST = "list"
    RESULTS = "results"
    LOGS = "logs"
    CONFIRM = "confirm"
    CONFIRM_DELETE = "confirm_delete"
    DONE = "done"
    CLARIFY = "clarify"
    ERROR = "error"


@dataclass
class PendingMissionAction:
    action: str
    mission_id: int
    stage: str = "confirm"
    expected_phrase: str = ""
    payload: dict[str, str] = field(default_factory=dict)


@dataclass
class MissionsPlan:
    task_type: MissionsTaskType
    mission_id: int | None = None
    status_filter: str | None = None
    limit: int = 25
    profile: MissionsProfile = MissionsProfile.LIST
    needs_clarification: bool = False
    clarification_question: str = ""
    raw_matches: list[str] = field(default_factory=list)
