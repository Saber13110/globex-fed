"""Tests classification intents tickets admin."""

from __future__ import annotations

from app.services.admin_client.tickets.tickets_intent import classify_tickets_intent
from app.services.admin_client.tickets.tickets_reconcile import reconcile_tickets_plan
from app.services.admin_client.tickets.tickets_types import TicketsTaskType


def test_intent_list_open():
    plan = classify_tickets_intent("liste les tickets ouverts")
    assert plan.task_type == TicketsTaskType.ticket_list
    assert plan.status_filter == "open"


def test_intent_summary():
    plan = classify_tickets_intent("résumé des tickets support")
    assert plan.task_type == TicketsTaskType.ticket_summary


def test_intent_detail_hash():
    plan = classify_tickets_intent("détail du ticket #12")
    assert plan.task_type == TicketsTaskType.ticket_detail
    assert plan.ticket_id == 12


def test_intent_write_reply_with_body():
    plan = classify_tickets_intent("réponds au ticket #5 avec merci pour votre patience")
    assert plan.task_type == TicketsTaskType.ticket_reply
    assert plan.ticket_id == 5
    assert "merci" in plan.reply_body.lower()
    assert plan.want_draft is False


def test_intent_write_reply_draft_on_pronoun():
    hist = "**Fiche ticket**\n#11 — SUP-2026-0011"
    plan = classify_tickets_intent("je veux que tu me repond a ce ticket", history_text=hist)
    assert plan.task_type == TicketsTaskType.ticket_reply
    assert plan.want_draft is True


def test_reconcile_no_search_when_status():
    plan = classify_tickets_intent("liste tickets pending")
    plan = reconcile_tickets_plan("liste tickets pending", plan)
    assert plan.status_filter == "pending"
    assert plan.search_query is None


def test_intent_followup_after_list():
    hist = "**Liste des tickets support**\n| 3 | TKT-003 | Problème colis | bob@test.com | open | medium |"
    plan = classify_tickets_intent("le 1", history_text=hist)
    assert plan.task_type == TicketsTaskType.ticket_detail
