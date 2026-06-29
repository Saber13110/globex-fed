"""Types partagés agent Security IDS admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SecurityTaskType(str, Enum):
    security_scan = "security_scan"
    security_incident_list = "security_incident_list"
    security_incident_detail = "security_incident_detail"
    security_incident_summary = "security_incident_summary"
    security_report = "security_report"
    ambiguous = "ambiguous"


class SecurityProfile(str, Enum):
    LIST = "list"
    DETAIL = "detail"
    SUMMARY = "summary"
    SCAN = "scan"
    REPORT = "report"
    CLARIFY = "clarify"
    ERROR = "error"


class SecurityToolError(Exception):
    """Échec outil sécurité admin."""


@dataclass
class SecurityPlan:
    task_type: SecurityTaskType
    incident_id: int | None = None
    status_filter: str | None = None
    severity_filter: str | None = None
    include_ai_scan: bool = False
    limit: int = 30
    want_pdf: bool = False
    profile: SecurityProfile = SecurityProfile.LIST
    raw_matches: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
