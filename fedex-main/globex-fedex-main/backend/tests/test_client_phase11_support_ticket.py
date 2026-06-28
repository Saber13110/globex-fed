"""Tests Phase 11 — ticket support intelligent."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.client_phase11.capabilities import CAP_SUPPORT_TICKET, has_support_ticket_capability
from app.services.client_phase11.router import reconcile_plan, try_client_support_ticket_turn
from app.services.client_phase11.router_prompt import TICKET_CONFIRMATION_MARKER
from app.services.client_phase11.ticket_draft_pointer import (
    TicketDraft,
    get_ticket_draft,
    set_ticket_draft,
)
from app.services.client_phase11.ticket_intent import (
    fallback_plan_from_message,
    is_support_workspace,
)
from app.services.support_ticket_service import normalize_ticket_category


def test_is_support_workspace_positive():
    assert is_support_workspace("ouvre un ticket colis endommagé")
    assert is_support_workspace("contactez l'admin mon colis est bloqué")
    assert is_support_workspace(
        "je vais faire une plaite et l'envoyer a l'admin que mon colis est bloque en douane"
    )


def test_is_support_workspace_excludes_other_phases():
    assert not is_support_workspace("rapport du jour par mail")
    assert not is_support_workspace("liste mes documents")
    assert not is_support_workspace("où est mon colis 881135077232")


def test_fallback_plan_open_ticket():
    plan = fallback_plan_from_message(
        "Mon colis est endommagé 881135077232, ouvre le ticket maintenant",
        lang="fr",
    )
    assert plan is not None
    assert plan["task_type"] == "open_support_ticket"
    assert plan["ready_to_execute"] is True


def test_reconcile_plan_maps_invalid_category():
    plan = reconcile_plan(
        "ticket support",
        {
            "task_type": "open_support_ticket",
            "answers": {
                "subject": "Test",
                "message": "Message suffisamment long pour le ticket.",
                "category": "delivery",
                "priority": "urgent",
                "tracking_number": "",
            },
            "ready_to_execute": False,
            "needs_clarification": False,
            "clarification_question": "",
        },
        lang="fr",
    )
    assert normalize_ticket_category(plan["answers"]["category"]) == "tracking"
    assert plan["answers"]["priority"] == "medium"


@patch("app.services.client_phase11.router.router_enabled", return_value=True)
@patch("app.services.client_phase11.router.has_support_ticket_capability", return_value=True)
@patch("app.services.client_phase11.router.plan_support_task")
def test_draft_confirmation_no_db_ticket(mock_plan, _cap, _router):
    mock_plan.return_value = {
        "task_type": "open_support_ticket",
        "assistant_intro": "",
        "answers": {
            "subject": "Colis endommagé",
            "message": "Le colis est arrivé avec le carton ouvert et l'article cassé.",
            "category": "tracking",
            "priority": "high",
            "tracking_number": "881135077232",
        },
        "ready_to_execute": False,
        "needs_clarification": False,
        "clarification_question": "",
    }
    user = SimpleNamespace(id=1, preferred_language="fr", email="u@test.com")
    session = SimpleNamespace(id=99)
    db = MagicMock()
    turn = try_client_support_ticket_turn(
        db, user, session, "ouvre un ticket colis endommagé", 1, ui_language="fr"
    )
    assert turn is not None
    assert turn["intent"] == "support_ticket_draft"
    assert TICKET_CONFIRMATION_MARKER in turn["reply"]


@patch("app.services.client_phase11.router.router_enabled", return_value=True)
@patch("app.services.client_phase11.router.has_support_ticket_capability", return_value=True)
@patch("app.services.client_phase11.router.execute_open_support_ticket")
@patch("app.services.client_phase11.router._last_bot_message_text")
@patch("app.services.client_phase11.router.get_ticket_draft")
def test_confirmation_followup_creates_ticket(mock_get_draft, mock_last_bot, mock_execute, _cap, _router):
    mock_last_bot.return_value = f"{TICKET_CONFIRMATION_MARKER} à l'équipe admin ?"
    mock_get_draft.return_value = TicketDraft(
        subject="Colis endommagé",
        message="Description détaillée du problème constaté à la livraison.",
        category="tracking",
        priority="high",
        tracking_number="881135077232",
    )
    mock_execute.return_value = {
        "reply": "**Ticket ouvert** — référence `TKT-1`.",
        "intent": "support_ticket_created",
        "ticket_number": "TKT-1",
        "ticket_id": 1,
    }
    user = SimpleNamespace(id=1, preferred_language="fr", email="u@test.com")
    session = SimpleNamespace(id=99)
    db = MagicMock()
    turn = try_client_support_ticket_turn(
        db, user, session, "oui envoie", 2, ui_language="fr"
    )
    assert turn is not None
    assert turn["intent"] == "support_ticket_created"
    mock_execute.assert_called_once()


@patch("app.services.client_phase11.router.router_enabled", return_value=True)
@patch("app.services.client_phase11.router.has_support_ticket_capability", return_value=False)
def test_capability_off_returns_none(_cap, _router):
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_client_support_ticket_turn(
        db, user, session, "ouvre un ticket support", 1, ui_language="fr"
    )
    assert turn is None


@patch("app.services.client_phase11.capabilities.get_settings")
def test_has_support_ticket_capability(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_capabilities=f"chat,{CAP_SUPPORT_TICKET}",
    )
    assert has_support_ticket_capability()


def test_ticket_draft_pointer_ttl():
    set_ticket_draft(
        123,
        {
            "subject": "Sujet test",
            "message": "Corps du message assez long pour validation.",
            "category": "other",
            "priority": "medium",
            "tracking_number": "",
        },
    )
    draft = get_ticket_draft(123)
    assert draft is not None
    assert draft.subject == "Sujet test"
