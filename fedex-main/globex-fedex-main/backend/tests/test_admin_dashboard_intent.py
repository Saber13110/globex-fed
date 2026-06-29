"""Tests classification intents dashboard admin."""

from __future__ import annotations

import pytest

from app.services.admin_client.dashboard.dashboard_intent import (
    DashboardTaskType,
    classify_dashboard_intent,
    plan_from_router_data,
)

_INTENT_CASES = [
    ("Résume l'état de la plateforme aujourd'hui", DashboardTaskType.platform_overview),
    ("Platform overview and KPI today", DashboardTaskType.platform_overview),
    ("Quelle est la santé du système ?", DashboardTaskType.platform_overview),
    ("Situation globale dashboard", DashboardTaskType.platform_overview),
    ("Tableau de bord stats", DashboardTaskType.platform_overview),
    ("Quels colis problématiques ?", DashboardTaskType.delayed_shipments),
    ("Liste des retards expédition", DashboardTaskType.delayed_shipments),
    ("Delayed shipments at risk", DashboardTaskType.delayed_shipments),
    ("Colis en retard globaux", DashboardTaskType.delayed_shipments),
    ("Prépare un rapport des retards", DashboardTaskType.quick_delay_report),
    ("Delay report with charts", DashboardTaskType.quick_delay_report),
    ("Rapport retards plateforme en pdf", DashboardTaskType.quick_delay_report),
    ("Activité récente plateforme", DashboardTaskType.recent_activity),
    ("Recent activity timeline", DashboardTaskType.recent_activity),
    ("What happened on the dashboard", DashboardTaskType.recent_activity),
    ("Conversations IA récentes", DashboardTaskType.recent_ai_conversations),
    ("Recent AI conversations assistant", DashboardTaskType.recent_ai_conversations),
    ("Audit récent logs admin", DashboardTaskType.recent_audit),
    ("Activité suspecte aujourd'hui", DashboardTaskType.recent_audit),
    ("Suspicious security activity", DashboardTaskType.recent_audit),
    ("Utilisateurs par rôle", DashboardTaskType.users_breakdown),
    ("Users by role breakdown", DashboardTaskType.users_breakdown),
    ("Répartition des comptes", DashboardTaskType.users_breakdown),
    ("Nouveaux utilisateurs cette semaine", DashboardTaskType.new_users_period),
    ("New users created this week", DashboardTaskType.new_users_period),
    ("Inscriptions récentes plateforme", DashboardTaskType.new_users_period),
    ("Rapport des retards et KPI", DashboardTaskType.quick_delay_report),
    ("Montre les retards puis les KPI", DashboardTaskType.delayed_shipments),
    ("Exporte le rapport des retards en pdf", DashboardTaskType.quick_delay_report),
    ("Combien de retards sur la plateforme ?", DashboardTaskType.delayed_shipments),
    ("Incidents ouverts et audit", DashboardTaskType.recent_audit),
    ("Métriques FedEx dashboard", DashboardTaskType.platform_overview),
]


@pytest.mark.parametrize("message,expected", _INTENT_CASES)
def test_classify_dashboard_intent_families(message, expected):
    plan = classify_dashboard_intent(message)
    assert plan.task_type == expected, f"{message!r} -> {plan.task_type}"


def test_classify_not_dashboard_ambiguous():
    plan = classify_dashboard_intent("suivi colis 817725683025")
    assert plan.task_type == DashboardTaskType.ambiguous


def test_classify_quick_delay_report_pdf_flag():
    plan = classify_dashboard_intent("Prépare un rapport des retards en pdf")
    assert plan.task_type == DashboardTaskType.quick_delay_report
    assert plan.include_pdf is True


def test_classify_audit_suspicious_flag():
    plan = classify_dashboard_intent("Activité suspecte dans les logs admin")
    assert plan.task_type == DashboardTaskType.recent_audit
    assert plan.suspicious_only is True


def test_plan_from_router_data():
    plan = plan_from_router_data(
        {
            "task_type": "new_users_period",
            "answers": {"period": "week", "limit": 5},
        }
    )
    assert plan is not None
    assert plan.task_type == DashboardTaskType.new_users_period
    assert plan.period == "week"
    assert plan.limit == 5
