"""Tests gate tickets vs users/tracking."""

from __future__ import annotations

from app.services.admin_client.intent_priority import should_route_tickets


def test_should_route_tickets_list():
    assert should_route_tickets("liste les tickets support ouverts")


def test_should_route_tickets_summary():
    assert should_route_tickets("résumé des tickets")


def test_should_not_route_tracking():
    assert not should_route_tickets("suivi 817725683025")


def test_should_not_route_users():
    assert not should_route_tickets("liste les utilisateurs suspendus")


def test_should_not_route_fedex_support_phone():
    assert not should_route_tickets("numéro support FedEx 1-800")


def test_should_route_ticket_in_context():
    hist = "**Liste des tickets support**\n| 1 | TKT-1 | Sujet | a@b.com | open | high |"
    assert should_route_tickets("détail du #1", history_text=hist)
