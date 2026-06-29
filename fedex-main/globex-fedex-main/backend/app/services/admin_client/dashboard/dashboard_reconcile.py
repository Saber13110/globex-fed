"""Reconcile plan dashboard — question_type + paramètres."""

from __future__ import annotations

import re

from app.services.admin_client.dashboard.dashboard_signals import normalize_message_text
from app.services.admin_client.dashboard.dashboard_types import (
    DashboardPlan,
    DashboardQuestionType,
    DashboardTaskType,
)


def infer_question_type(message: str, plan: DashboardPlan) -> DashboardQuestionType:
    text = normalize_message_text(message)
    if plan.task_type == DashboardTaskType.delayed_shipments:
        return DashboardQuestionType.LIST
    if plan.task_type == DashboardTaskType.recent_activity:
        return DashboardQuestionType.LIST
    if plan.task_type == DashboardTaskType.recent_audit and plan.suspicious_only:
        return DashboardQuestionType.LIST
    if re.search(r"\b(explique|simplement|en clair|decortique)\b", text):
        return DashboardQuestionType.EXPLAIN
    if re.search(r"\b(probleme|souci|panne|ca va|alerte|normal)\b", text):
        return DashboardQuestionType.STATUS
    if re.search(r"\b(priorit|important|surveiller|chiffres? cles?|principaux? kpi)\b", text):
        return DashboardQuestionType.KPI_LIST
    if re.search(r"\b(liste|montre|affiche|timeline|evenements?)\b", text):
        return DashboardQuestionType.LIST
    if re.search(r"\b(resume|recap|synthese|bilan|etat|overview)\b", text):
        return DashboardQuestionType.SUMMARY
    return DashboardQuestionType.SUMMARY


def reconcile_dashboard_plan(message: str, plan: DashboardPlan) -> DashboardPlan:
    text = normalize_message_text(message)

    if re.search(r"\b(suspect|anomal|intrusion|ids)\b", text):
        if plan.task_type in (DashboardTaskType.recent_audit, DashboardTaskType.platform_overview):
            plan.task_type = DashboardTaskType.recent_audit
            plan.suspicious_only = True

    if re.search(r"\b(pdf|exporte?|telecharge)\b", text) and re.search(r"\bretard", text):
        plan.include_pdf = True
        if plan.task_type == DashboardTaskType.platform_overview:
            plan.task_type = DashboardTaskType.quick_delay_report

    if re.search(r"\b(graphique|chart|visualis)\b", text):
        plan.include_charts = True

    plan.question_type = infer_question_type(message, plan)
    return plan
