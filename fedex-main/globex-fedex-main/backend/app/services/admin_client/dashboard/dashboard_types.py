"""Types partagés dashboard admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DashboardTaskType(str, Enum):
    platform_overview = "platform_overview"
    delayed_shipments = "delayed_shipments"
    quick_delay_report = "quick_delay_report"
    recent_activity = "recent_activity"
    recent_ai_conversations = "recent_ai_conversations"
    recent_audit = "recent_audit"
    users_breakdown = "users_breakdown"
    new_users_period = "new_users_period"
    ambiguous = "ambiguous"


class DashboardQuestionType(str, Enum):
    SUMMARY = "summary"
    STATUS = "status"
    KPI_LIST = "kpi_list"
    EXPLAIN = "explain"
    LIST = "list"


@dataclass
class DashboardPlan:
    task_type: DashboardTaskType
    period: str = "today"
    role: str = "all"
    status: str = "all"
    limit: int = 10
    suspicious_only: bool = False
    include_charts: bool = False
    include_pdf: bool = False
    raw_matches: list[str] = field(default_factory=list)
    question_type: DashboardQuestionType = DashboardQuestionType.SUMMARY
    signal_scores: dict[str, float] = field(default_factory=dict)
    needs_router: bool = False
