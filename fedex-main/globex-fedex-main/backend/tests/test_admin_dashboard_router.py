"""Tests routeur dashboard Ollama JSON fallback."""

from __future__ import annotations

from unittest.mock import patch

from app.services.admin_client.dashboard.dashboard_router import plan_admin_dashboard_task


@patch("app.services.admin_client.dashboard.dashboard_router.call_ollama_agent_plan")
def test_plan_admin_dashboard_task_delayed(mock_call):
    mock_call.return_value = (
        '{"task_type":"delayed_shipments","answers":{"limit":5},"ready_to_execute":true}'
    )
    plan = plan_admin_dashboard_task("montre moi les retards globaux")
    assert plan is not None
    assert plan["task_type"] == "delayed_shipments"


@patch("app.services.admin_client.dashboard.dashboard_router.call_ollama_agent_plan")
def test_plan_admin_dashboard_task_ambiguous_returns_none(mock_call):
    mock_call.return_value = '{"task_type":"ambiguous","ready_to_execute":false}'
    assert plan_admin_dashboard_task("bonjour") is None
