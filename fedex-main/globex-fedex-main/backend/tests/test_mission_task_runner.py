"""Tests — catalogue et runner missions."""

from __future__ import annotations

from app.services.mission_task_catalog import (
    catalog_for_api,
    chain_metadata_for_task,
    get_task_spec,
    normalize_agent_type,
    runtime_agent_type,
    tasks_for_agent,
)
from app.services.mission_task_runner import (
    assess_task_role,
    resolve_task_from_node,
    sort_task_nodes,
    split_prior_context,
    workflow_agent_for_task,
)


def test_normalize_agent_type_legacy_aliases():
    assert normalize_agent_type("notifications") == "security"
    assert normalize_agent_type("summary") == "reports"
    assert runtime_agent_type("security") == "notifications"
    assert runtime_agent_type("reports") == "summary"


def test_catalog_task_spec_users_suspend():
    spec = get_task_spec("users", "user_suspend")
    assert spec is not None
    assert spec.requires_description is True
    assert "Suspendre" in spec.default_prompt


def test_assess_task_role_catalog_match_skips_keywords():
    role = assess_task_role("", "users", task_id="user_list")
    assert role["matches"] is True
    role_bad = assess_task_role("ticket urgent", "users", task_id="user_list")
    assert role_bad["matches"] is True


def test_assess_task_role_free_text_keywords():
    role = assess_task_role("lister les logs récents", "logs")
    assert role["matches"] is True
    role_mismatch = assess_task_role("répondre au ticket client #42", "users")
    assert role_mismatch["matches"] is False
    assert role_mismatch["suggested_agent"] == "support"


def test_resolve_task_from_node_catalog():
    resolved = resolve_task_from_node(
        "security",
        {"taskId": "incident_list", "label": "Incidents", "description": ""},
    )
    assert "incidents de sécurité" in resolved["task_text"].lower()
    assert resolved["task_id"] == "incident_list"
    assert resolved["action_type"] == "analyze_security"


def test_resolve_task_incident_list_ignores_prior_summary():
    prior = "| 12 | 2026-01-01 | high | x | open | a@b.com | A |"
    resolved = resolve_task_from_node(
        "security",
        {"taskId": "incident_list", "description": ""},
        prior_summary=prior,
    )
    assert prior not in resolved["task_text"]


def test_resolve_task_incident_detail_includes_prior_summary():
    prior = "**Incidents sécurité**\n| 12 | 2026-01-01 | high | x | open | a@b.com | A |"
    resolved = resolve_task_from_node(
        "security",
        {"taskId": "incident_detail", "description": "#2"},
        prior_summary=prior,
    )
    assert prior in resolved["task_text"]
    assert "Précisions : #2" in resolved["task_text"]


def test_resolve_task_from_node_custom_requires_description():
    resolved = resolve_task_from_node(
        "users",
        {"taskId": "custom", "description": "Suspendre compte test@example.com"},
    )
    assert "test@example.com" in resolved["task_text"]


def test_workflow_agent_for_task_finds_upstream_agent():
    wf = {
        "nodes": [
            {"id": "t1", "type": "timing", "data": {}},
            {"id": "a1", "type": "agent", "data": {"agentType": "logs"}},
            {"id": "k1", "type": "task", "data": {"description": "x"}},
        ],
        "edges": [
            {"from": "t1", "to": "a1"},
            {"from": "a1", "to": "k1"},
        ],
    }
    assert workflow_agent_for_task(wf, "k1") == "logs"


def test_workflow_agent_for_task_interleaved_agents():
    """Déclencheur → Agent → Tâche → Agent → Tâche (phase 2 structure)."""
    wf = {
        "nodes": [
            {"id": "t0", "type": "timing", "data": {}},
            {"id": "a1", "type": "agent", "data": {"agentType": "security"}},
            {"id": "k1", "type": "task", "data": {"taskId": "incident_list"}},
            {"id": "a2", "type": "agent", "data": {"agentType": "security"}},
            {"id": "k2", "type": "task", "data": {"taskId": "incident_detail"}},
        ],
        "edges": [
            {"from": "t0", "to": "a1"},
            {"from": "a1", "to": "k1"},
            {"from": "k1", "to": "a2"},
            {"from": "a2", "to": "k2"},
        ],
    }
    assert workflow_agent_for_task(wf, "k1") == "security"
    assert workflow_agent_for_task(wf, "k2") == "security"


def test_workflow_agent_for_task_different_agents_per_task():
    wf = {
        "nodes": [
            {"id": "t0", "type": "timing", "data": {}},
            {"id": "a1", "type": "agent", "data": {"agentType": "security"}},
            {"id": "k1", "type": "task", "data": {}},
            {"id": "a2", "type": "agent", "data": {"agentType": "support"}},
            {"id": "k2", "type": "task", "data": {}},
        ],
        "edges": [
            {"from": "t0", "to": "a1"},
            {"from": "a1", "to": "k1"},
            {"from": "k1", "to": "a2"},
            {"from": "a2", "to": "k2"},
        ],
    }
    assert workflow_agent_for_task(wf, "k1") == "security"
    assert workflow_agent_for_task(wf, "k2") == "support"


def test_sort_task_nodes_by_bfs_then_priority():
    nodes = [
        {"id": "a", "data": {"priority": 50}},
        {"id": "b", "data": {"priority": 10}},
    ]
    ordered = sort_task_nodes(nodes)
    assert [n["id"] for n in ordered] == ["a", "b"]


def test_catalog_for_api_non_empty():
    entries = catalog_for_api()
    assert len(entries) >= 20
    assert any(e["agent_type"] == "security" for e in entries)


def test_catalog_for_api_includes_chain_metadata():
    entries = catalog_for_api()
    incident_detail = next(
        e for e in entries if e["agent_type"] == "security" and e["task_id"] == "incident_detail"
    )
    assert incident_detail["consumes_prior"] is True
    assert incident_detail["produces_context"] is True
    assert incident_detail["terminal"] is False

    log_export = next(
        e for e in entries if e["agent_type"] == "logs" and e["task_id"] == "log_export_pdf"
    )
    assert log_export["terminal"] is True
    assert log_export["produces_context"] is False


def test_chain_metadata_defaults_for_unknown_task():
    meta = chain_metadata_for_task("users", "unknown_task")
    assert meta == {"consumes_prior": False, "produces_context": False, "terminal": False}


def test_chain_metadata_entry_tasks_do_not_consume_prior():
    for task_id in ("log_list", "incident_list", "ticket_list", "user_list", "tracking_analyze"):
        agent = {
            "log_list": "logs",
            "incident_list": "security",
            "ticket_list": "support",
            "user_list": "users",
            "tracking_analyze": "tracking",
        }[task_id]
        spec = get_task_spec(agent, task_id)
        assert spec is not None
        assert spec.consumes_prior is False
        assert spec.produces_context is True


def test_chain_metadata_consumer_tasks():
    consumers = [
        ("security", "incident_detail"),
        ("support", "ticket_reply"),
        ("users", "user_suspend"),
        ("tracking", "tracking_export_email"),
    ]
    for agent_type, task_id in consumers:
        spec = get_task_spec(agent_type, task_id)
        assert spec is not None, f"{agent_type}/{task_id}"
        assert spec.consumes_prior is True


def test_tasks_for_agent_security_includes_incident_list():
    tasks = tasks_for_agent("notifications")
    ids = {t.task_id for t in tasks}
    assert "incident_list" in ids
