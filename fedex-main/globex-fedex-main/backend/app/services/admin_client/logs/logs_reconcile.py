"""Nettoyage plan logs — filtres cohérents."""

from __future__ import annotations

import re

from app.services.admin_client.logs.logs_followup import extract_log_ref
from app.services.admin_client.logs.logs_patterns import is_user_scoped_logs_message
from app.services.admin_client.logs.logs_types import LogsPlan, LogsProfile, LogsTaskType

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def reconcile_logs_plan(message: str, plan: LogsPlan, *, history_text: str = "") -> LogsPlan:
    if is_user_scoped_logs_message(message):
        return plan

    lid = plan.log_id or extract_log_ref(message, history_text=history_text)
    if lid:
        plan.log_id = lid

    if not plan.user_query:
        m = _EMAIL_RE.search(message or "")
        if m:
            plan.user_query = m.group(0)

    if plan.task_type in {LogsTaskType.log_list, LogsTaskType.log_search, LogsTaskType.log_anomalies}:
        if plan.level_filter or plan.category_filter or plan.action_filter or plan.period_hours:
            if not plan.search_query or plan.search_query in {
                plan.level_filter, plan.category_filter, plan.action_filter
            }:
                pass

    _PROFILE = {
        LogsTaskType.log_list: LogsProfile.LIST,
        LogsTaskType.log_search: LogsProfile.LIST,
        LogsTaskType.log_detail: LogsProfile.DETAIL,
        LogsTaskType.log_summary_user_day: LogsProfile.SUMMARY,
        LogsTaskType.log_summary_platform_day: LogsProfile.SUMMARY,
        LogsTaskType.log_anomalies: LogsProfile.ANOMALIES,
        LogsTaskType.log_open_conversation: LogsProfile.CONVERSATION,
        LogsTaskType.log_suspend_user: LogsProfile.CONFIRM,
    }
    if plan.profile == LogsProfile.LIST and plan.task_type in _PROFILE:
        plan.profile = _PROFILE[plan.task_type]

    return plan
