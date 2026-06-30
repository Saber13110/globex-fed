"""Tests — routage outil Security Agent (pas analyze_logs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.admin_agent_tools import parse_security_intent, resolve_tool_for_mission
from app.services.mission_task_catalog import get_task_spec
from app.services.mission_task_runner import catalog_mission_tool, resolve_task_from_node, split_prior_context


def test_incident_list_catalog_uses_analyze_security():
    spec = get_task_spec("security", "incident_list")
    assert spec is not None
    assert spec.tool_hint == "analyze_security"
    resolved = resolve_task_from_node("security", {"taskId": "incident_list", "description": ""})
    assert catalog_mission_tool(resolved) == "analyze_security"


def test_parse_security_intent_incidents():
    assert parse_security_intent("Lister les incidents de sécurité récents.") == "analyze_security"


def test_parse_security_intent_notifications():
    assert parse_security_intent("Lister les notifications admin non lues.") == "analyze_notifications"


def test_resolve_tool_security_not_logs():
    mission = MagicMock(agent_type="notifications")
    tool = resolve_tool_for_mission(mission, "Lister les incidents de sécurité récents.")
    assert tool == "analyze_security"
    assert tool != "analyze_logs"


@patch("app.services.admin_agent_runtime.plan_admin_mission")
@patch("app.services.admin_agent_runtime._execute_security_tool")
def test_execute_mission_catalog_overrides_brain_logs(mock_sec, mock_plan):
    from app.models.agent_mission import AgentMission
    from app.models.agent_mission_step import AgentMissionStep
    from app.services.admin_agent_runtime import execute_admin_mission_task

    mock_plan.return_value = {
        "objective": "Lister incidents",
        "action_tool": "analyze_logs",
        "ready_to_execute": True,
    }
    mock_sec.return_value = {"task_answer": "ok", "action": "analyze_security", "deterministic_compose": True}

    mission = AgentMission(agent_type="notifications", task_description="x", max_items=10)
    step = AgentMissionStep(mission_id=1, step_order=1, title="t", description="d", action_type="x")
    db = MagicMock()

    execute_admin_mission_task(
        db,
        mission,
        step,
        task="Lister les incidents de sécurité récents.",
        actor_admin_id=1,
        context={},
        catalog_tool_hint="analyze_security",
        source_agent_type="security",
        catalog_task_id="incident_list",
    )

    mock_sec.assert_called_once()
    assert mock_sec.call_args.kwargs["tool"] == "analyze_security"
    assert mock_sec.call_args.kwargs["catalog_task_id"] == "incident_list"


def test_split_prior_context():
    task = "Analyser un incident.\n\nPrécisions : #2\n\nContexte étape précédente : | 12 |"
    user_part, prior = split_prior_context(task)
    assert "Précisions : #2" in user_part
    assert prior.startswith("| 12 |")


def test_incident_list_uses_compose_not_full_context():
    from app.services.mission_task_runner import security_plan_for_catalog_task, task_wants_security_incident_list

    plan = security_plan_for_catalog_task("incident_list")
    assert plan is not None
    assert plan.profile.value == "list"
    assert task_wants_security_incident_list("Lister les incidents de sécurité récents.", "incident_list")


@patch("app.services.admin_client.security.security_tool.get_incident_detail")
def test_security_detail_resolves_hash_row_from_prior_context(mock_detail):
    from datetime import datetime, timezone

    from app.models.agent_mission import AgentMission
    from app.models.agent_mission_step import AgentMissionStep
    from app.services.admin_agent_runtime import _execute_security_tool
    from app.services.mission_task_runner import PRIOR_CONTEXT_MARKER, resolve_task_from_node

    mock_detail.return_value = {
        "id": 11,
        "severity": "high",
        "threat_type": "prompt_injection",
        "status": "open",
        "title": "Inc B",
        "user_email": "b@b.com",
        "created_at": datetime.now(timezone.utc),
        "summary": "Test",
        "source": "rule_engine",
    }

    prior = (
        "**Incidents sécurité** (statut=open)\n"
        "| 12 | 2026-01-01 | high | prompt_injection | open | a@b.com | Inc A |\n"
        "| 11 | 2026-01-01 | high | prompt_injection | open | b@b.com | Inc B |"
    )
    resolved = resolve_task_from_node(
        "security",
        {"taskId": "incident_detail", "description": "#2"},
        prior_summary=prior,
    )
    task = resolved["task_text"]
    assert PRIOR_CONTEXT_MARKER in task

    mission = AgentMission(agent_type="notifications", task_description="x", max_items=10)
    step = AgentMissionStep(mission_id=1, step_order=2, title="t", description="d", action_type="x")
    steps: list = []
    db = MagicMock()
    db.get.return_value = object()

    out = _execute_security_tool(
        db,
        mission,
        step,
        tool="analyze_security",
        task=task,
        steps=steps,
        catalog_task_id="incident_detail",
    )

    mock_detail.assert_called_once()
    assert mock_detail.call_args[0][1] == 11
    assert out.get("security_incident_id") == 11
    assert "Inc B" in (out.get("task_answer") or "")
    assert out.get("deterministic_compose") is True
