"""Tests corrections conversation live tickets."""

from __future__ import annotations

from app.services.admin_client.intent_priority import should_route_tickets, should_route_users
from app.services.admin_client.tickets.tickets_followup import extract_list_row_index, extract_ticket_ref
from app.services.admin_client.tickets.tickets_intent import classify_tickets_intent
from app.services.admin_client.tickets.tickets_reconcile import reconcile_tickets_plan
from app.services.admin_client.tickets.tickets_types import TicketsTaskType


def test_details_plural_open_not_list_only():
    plan = classify_tickets_intent("donne moi detailles des tickets ouverts")
    assert plan.task_type == TicketsTaskType.ticket_details_batch
    assert plan.status_filter == "open"


def test_ordinal_second_ticket_from_history():
    hist = (
        "**Liste des tickets support**\n"
        "| 11 | SUP-2026-0011 | Blocage | a@b.com | open | medium |\n"
        "| 10 | SUP-2026-0010 | Chat | a@b.com | open | medium |"
    )
    plan = classify_tickets_intent("donne moi detaille de 2eme ticket", history_text=hist)
    assert plan.task_type == TicketsTaskType.ticket_detail
    ref = extract_ticket_ref("donne moi detaille de 2eme ticket", history_text=hist)
    assert ref == 10


def test_ordinal_first_ticket_from_history():
    hist = "**Liste des tickets support**\n| 11 | SUP-2026-0011 | Blocage | a@b.com | open | medium |"
    plan = classify_tickets_intent("donne moi detaille du 1er ticket", history_text=hist)
    assert plan.task_type == TicketsTaskType.ticket_detail
    ref = extract_ticket_ref("donne moi detaille du 1er ticket", history_text=hist)
    assert ref == 11
    assert extract_list_row_index("detaille du 1er ticket") == 0


def test_reply_ce_ticket_with_draft_intent():
    hist = "**Fiche ticket**\n#11 — SUP-2026-0011"
    plan = classify_tickets_intent("je veux que tu me repond a ce ticket", history_text=hist)
    assert plan.task_type == TicketsTaskType.ticket_reply
    assert plan.want_draft is True
    assert should_route_tickets("je veux que tu me repond a ce ticket", history_text=hist)


def test_tickets_user_abdo_not_users_agent():
    assert should_route_tickets("donne moi les ticket du user abdo")
    assert not should_route_users("donne moi les ticket du user abdo")


def test_tickets_by_email():
    plan = classify_tickets_intent("donne moi les tickets de abdo@gmail.com")
    assert plan.task_type == TicketsTaskType.ticket_list
    plan = reconcile_tickets_plan("donne moi les tickets de abdo@gmail.com", plan)
    assert plan.search_query == "abdo@gmail.com"
