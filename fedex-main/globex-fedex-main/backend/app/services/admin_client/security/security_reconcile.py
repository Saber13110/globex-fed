"""Nettoyage plan Security IDS."""

from __future__ import annotations

from app.services.admin_client.security.security_followup import extract_incident_ref
from app.services.admin_client.security.security_patterns import is_logs_anomaly_scope
from app.services.admin_client.security.security_types import SecurityPlan, SecurityProfile, SecurityTaskType


def reconcile_security_plan(
    message: str,
    plan: SecurityPlan,
    *,
    history_text: str = "",
) -> SecurityPlan:
    if is_logs_anomaly_scope(message):
        return plan

    iid = plan.incident_id or extract_incident_ref(message, history_text=history_text)
    if iid:
        plan.incident_id = iid

    _PROFILE = {
        SecurityTaskType.security_incident_list: SecurityProfile.LIST,
        SecurityTaskType.security_incident_detail: SecurityProfile.DETAIL,
        SecurityTaskType.security_incident_summary: SecurityProfile.SUMMARY,
        SecurityTaskType.security_scan: SecurityProfile.SCAN,
        SecurityTaskType.security_report: SecurityProfile.REPORT,
    }
    if plan.task_type in _PROFILE:
        plan.profile = _PROFILE[plan.task_type]

    if plan.task_type == SecurityTaskType.security_incident_list and not plan.status_filter:
        plan.status_filter = "active"

    return plan
