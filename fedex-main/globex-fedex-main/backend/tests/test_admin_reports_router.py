"""Tests routeur reports admin."""

from __future__ import annotations

from unittest.mock import patch

from app.services.admin_client.reports.reports_intent import (
    clarify_plan_from_router,
    plan_from_router_data,
)
from app.services.admin_client.reports.reports_pipeline import detect_intent
from app.services.admin_client.reports.reports_router import plan_admin_reports_task
from app.services.admin_client.reports.reports_types import ReportsProfile, ReportsTaskType
from app.services.admin_client.reports.reports_workspace import (
    is_reports_workspace,
    score_reports_soft,
)


def test_score_reports_soft_list_all():
    assert score_reports_soft("liste moi tous les reports") >= 2.0
    assert is_reports_workspace("liste moi tous les reports")


def test_plan_from_router_data_list():
    plan = plan_from_router_data(
        {
            "task_type": "report_list_recent",
            "answers": {},
            "ready_to_execute": True,
        }
    )
    assert plan is not None
    assert plan.task_type == ReportsTaskType.report_list_recent


def test_clarify_plan_from_router():
    plan = clarify_plan_from_router(
        {
            "task_type": "ambiguous",
            "needs_clarification": True,
            "clarification_question": "Voulez-vous lister ou prévisualiser ?",
        }
    )
    assert plan.needs_clarification is True
    assert plan.profile == ReportsProfile.CLARIFY
    assert "prévisualiser" in plan.clarification_question


@patch("app.services.admin_client.reports.reports_router.call_ollama_agent_plan")
def test_router_clarification(mock_ollama):
    mock_ollama.return_value = """{
      "task_type": "ambiguous",
      "answers": {},
      "ready_to_execute": false,
      "needs_clarification": true,
      "clarification_question": "Souhaitez-vous lister les exports ou en prévisualiser un ?"
    }"""
    routed = plan_admin_reports_task("reports")
    assert routed is not None
    assert routed["needs_clarification"] is True


@patch("app.services.admin_client.reports.reports_router.call_ollama_agent_plan")
def test_detect_intent_bare_reports_default_clarify(mock_ollama):
    mock_ollama.return_value = None
    plan = detect_intent("reports", ui_language="fr")
    assert plan is not None
    assert plan.needs_clarification is True
    assert plan.profile == ReportsProfile.CLARIFY


@patch("app.services.admin_client.reports.reports_router.call_ollama_agent_plan")
def test_detect_intent_router_list(mock_ollama):
    mock_ollama.return_value = """{
      "task_type": "report_list_recent",
      "answers": {},
      "ready_to_execute": true,
      "needs_clarification": false,
      "clarification_question": ""
    }"""
    plan = detect_intent("montre moi ce truc reports stp", ui_language="fr")
    assert plan is not None
    assert plan.task_type == ReportsTaskType.report_list_recent
