"""Tests — compatibilité enchaînement tâches mission."""

from __future__ import annotations

from app.services.mission_chain_context import extract_chain_context
from app.services.mission_task_handoff import validate_task_handoff


def test_security_incident_list_to_logs_log_detail_rejected():
    msg = validate_task_handoff(
        "security",
        "incident_list",
        "logs",
        "log_detail",
        has_prior_output=True,
    )
    assert msg is not None
    assert "incident" in msg.lower()
    assert "Détail incident" in msg or "détail incident" in msg.lower() or "Security" in msg


def test_security_incident_list_to_incident_detail_allowed():
    assert (
        validate_task_handoff(
            "security",
            "incident_list",
            "security",
            "incident_detail",
            has_prior_output=True,
        )
        is None
    )


def test_security_incident_list_to_support_ticket_detail_allowed():
    assert (
        validate_task_handoff(
            "security",
            "incident_list",
            "support",
            "ticket_detail",
            has_prior_output=True,
        )
        is None
    )


def test_extract_chain_context_security_table_not_ticket_ids():
    answer = (
        "**Incidents sécurité** (statut=open)\n"
        "| 12 | 2026-06-28 | high | prompt_injection | open | amine@gmail.com | titre |\n"
        "| 4 | 2026-06-15 | high | prompt_injection | open | amine@gmail.com | titre2 |"
    )
    ctx = extract_chain_context({"task_answer": answer}, task_id="incident_list", agent_type="security")
    assert ctx.get("security_incident_ids") == [12, 4]
    assert "ticket_ids" not in ctx
