"""Tests — chaînage structuré missions (phase 2)."""

from __future__ import annotations

from app.services.mission_chain_context import (
    advance_chain_state,
    enrich_description_from_chain,
    extract_chain_context,
    format_chain_context_block,
    rebuild_chain_state_from_outputs,
)
from app.services.mission_task_catalog import get_task_spec
from app.services.mission_task_runner import resolve_task_from_node


def test_extract_chain_context_from_security_list_output():
    output = {
        "task_answer": "| 12 | 2026-01-01 | high | x | open | a@b.com | A |",
        "chain_context": {"security_incident_ids": [12, 11]},
    }
    ctx = extract_chain_context(output, task_id="incident_list", agent_type="security")
    assert ctx["security_incident_ids"] == [12, 11]


def test_advance_chain_state_list_then_detail():
    list_out = {
        "task_id": "incident_list",
        "task_answer": "**Incidents**\n| 12 | ... |\n| 11 | ... |",
        "chain_context": {"security_incident_ids": [12, 11]},
    }
    prior, ctx = advance_chain_state("", {}, list_out, task_id="incident_list", agent_type="security")
    assert "Incidents" in prior
    assert ctx["security_incident_ids"] == [12, 11]

    detail_out = {
        "task_id": "incident_detail",
        "task_answer": "Fiche incident #11",
        "security_incident_id": 11,
        "chain_context": {"security_incident_id": 11},
    }
    prior2, ctx2 = advance_chain_state(prior, ctx, detail_out, task_id="incident_detail", agent_type="security")
    assert "Fiche incident" in prior2
    assert ctx2["security_incident_id"] == 11


def test_advance_chain_state_terminal_export_keeps_prior_list():
    list_out = {
        "task_answer": "liste incidents",
        "chain_context": {"security_incident_ids": [12, 11]},
    }
    prior, ctx = advance_chain_state("", {}, list_out, task_id="incident_list", agent_type="security")

    export_out = {"task_answer": "PDF généré", "file_url": "/x.pdf"}
    prior2, ctx2 = advance_chain_state(
        prior, ctx, export_out, task_id="log_export_pdf", agent_type="logs"
    )
    assert prior2 == "liste incidents"
    assert ctx2 == ctx


def test_enrich_description_does_not_override_user_hash():
    spec = get_task_spec("security", "incident_detail")
    desc = enrich_description_from_chain(
        "#2",
        spec,
        {"security_incident_ids": [12, 11]},
    )
    assert desc == "#2"


def test_enrich_description_fills_empty_incident_detail():
    spec = get_task_spec("security", "incident_detail")
    desc = enrich_description_from_chain("", spec, {"security_incident_ids": [12]})
    assert desc == "incident #12"


def test_resolve_task_includes_structured_block_for_consumer():
    prior = "| 12 | 2026-01-01 | high | x | open | a@b.com | A |"
    resolved = resolve_task_from_node(
        "security",
        {"taskId": "incident_detail", "description": "#2"},
        prior_summary=prior,
        chain_context={"security_incident_ids": [12, 11]},
    )
    assert "Contexte structuré" in resolved["task_text"]
    assert "#12" in resolved["task_text"]
    assert "Précisions : #2" in resolved["task_text"]


def test_resolve_task_list_still_ignores_chain():
    resolved = resolve_task_from_node(
        "security",
        {"taskId": "incident_list"},
        prior_summary="ancien contexte",
        chain_context={"security_incident_ids": [12]},
    )
    assert "ancien contexte" not in resolved["task_text"]
    assert "Contexte structuré" not in resolved["task_text"]


def test_format_chain_context_block_empty():
    assert format_chain_context_block({}) == ""


def test_rebuild_chain_state_from_outputs_sequence():
    outputs = [
        (
            {"task_answer": "list", "chain_context": {"security_incident_ids": [12, 11]}},
            "incident_list",
            "security",
        ),
        (
            {"task_answer": "fiche", "security_incident_id": 11, "chain_context": {"security_incident_id": 11}},
            "incident_detail",
            "security",
        ),
    ]
    prior, ctx, prior_agent, prior_task_id = rebuild_chain_state_from_outputs(outputs)
    assert prior == "fiche"
    assert ctx["security_incident_id"] == 11
    assert prior_agent == "security"
    assert prior_task_id == "incident_detail"


def test_handoff_cross_agent_passes_prior_for_consuming_task():
    from app.services.mission_chain_context import handoff_context_for_next_task

    text = "**Incidents sécurité**\n| 12 | ... | amine@gmail.com |"
    summary, ctx = handoff_context_for_next_task(
        text,
        {"security_incident_ids": [12, 11]},
        prior_agent="security",
        next_agent="support",
        next_task_id="ticket_detail",
        prior_task_id="incident_list",
    )
    assert "Incidents sécurité" in summary
    assert ctx["security_incident_ids"] == [12, 11]
    assert ctx["user_email"] == "amine@gmail.com"
    assert ctx["prior_agent_type"] == "security"


def test_handoff_cross_agent_skips_non_consumer():
    from app.services.mission_chain_context import handoff_context_for_next_task

    summary, ctx = handoff_context_for_next_task(
        "liste incidents",
        {"security_incident_ids": [12]},
        prior_agent="security",
        next_agent="support",
        next_task_id="ticket_list",
    )
    assert summary == ""
    assert ctx == {}


def test_resolve_cross_agent_ticket_detail_gets_prior():
    prior = "**Incidents**\n| 12 | amine@gmail.com | titre |"
    resolved = resolve_task_from_node(
        "support",
        {"taskId": "ticket_detail", "description": ""},
        prior_summary=prior,
        chain_context={
            "prior_agent_type": "security",
            "security_incident_ids": [12],
            "user_email": "amine@gmail.com",
        },
    )
    assert "Contexte étape précédente" in resolved["task_text"]
    assert "Security" in resolved["task_text"] or "security" in resolved["task_text"].lower()
    assert "amine@gmail.com" in resolved["task_text"]


def test_handoff_same_agent_keeps_summary():
    from app.services.mission_chain_context import handoff_context_for_next_task

    text = "tableau incidents"
    summary, ctx = handoff_context_for_next_task(
        text,
        {"security_incident_ids": [12, 11]},
        prior_agent="security",
        next_agent="security",
        next_task_id="incident_detail",
    )
    assert summary == text
    assert ctx["security_incident_ids"] == [12, 11]
