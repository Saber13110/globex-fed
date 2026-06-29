"""Tests intents centre de rapports."""

from __future__ import annotations

from app.services.admin_client.reports.reports_intent import classify_reports_intent
from app.services.admin_client.reports.reports_types import ReportsTaskType


def test_intent_preview():
    plan = classify_reports_intent("Prévisualise le dernier export")
    assert plan.task_type == ReportsTaskType.report_preview


def test_intent_redownload():
    plan = classify_reports_intent("Re-télécharge le dernier export Excel")
    assert plan.task_type == ReportsTaskType.report_redownload
    assert plan.format_filter == "xlsx"


def test_intent_share_with_run_id():
    plan = classify_reports_intent("Partage le rapport 1 a bob@test.com")
    assert plan.task_type == ReportsTaskType.report_share
    assert plan.run_id == 1


def test_intent_slug_hint_tracking():
    plan = classify_reports_intent("Previsualise le rapport tracking history")
    assert plan.slug_hint == "tracking-history"


def test_intent_share():
    plan = classify_reports_intent("Partage le rapport à bob@test.com")
    assert plan.task_type == ReportsTaskType.report_share


def test_intent_list_recent():
    plan = classify_reports_intent("Liste des exports récents")
    assert plan.task_type == ReportsTaskType.report_list_recent


def test_intent_list_all_reports():
    plan = classify_reports_intent("liste moi tous les reports")
    assert plan.task_type == ReportsTaskType.report_list_recent


def test_intent_bare_reports_needs_router():
    plan = classify_reports_intent("reports")
    assert plan.task_type == ReportsTaskType.ambiguous
    assert plan.needs_router is True
