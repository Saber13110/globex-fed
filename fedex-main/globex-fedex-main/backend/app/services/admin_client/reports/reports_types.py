"""Types partagés agent Reports admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReportsTaskType(str, Enum):
    report_preview = "report_preview"
    report_list_recent = "report_list_recent"
    report_redownload = "report_redownload"
    report_share = "report_share"
    ambiguous = "ambiguous"


class ReportsProfile(str, Enum):
    PREVIEW = "preview"
    LIST = "list"
    DOWNLOAD = "download"
    SHARE_PROMPT = "share_prompt"
    SHARE_DONE = "share_done"
    CLARIFY = "clarify"
    CONSULT = "consult"


class ReportsToolError(Exception):
    """Échec outil reports admin."""


@dataclass
class ReportsPlan:
    task_type: ReportsTaskType
    run_id: int | None = None
    run_selector: str = "latest"  # latest | by_id | by_name
    format_filter: str | None = None  # xlsx | csv | json | pdf
    slug_hint: str | None = None  # tracking-history | financial-summary | ...
    search_filter: str | None = None
    limit: int = 15
    recipient_query: str = ""
    profile: ReportsProfile = ReportsProfile.LIST
    raw_matches: list[str] = field(default_factory=list)
    needs_router: bool = False
    needs_clarification: bool = False
    clarification_question: str = ""


@dataclass
class PendingShareAction:
    run_id: int
    recipient_emails: list[str]
    run_name: str = ""
