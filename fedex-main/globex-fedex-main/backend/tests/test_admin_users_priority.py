"""Tests gate utilisateurs vs dashboard/reports/tracking."""

from __future__ import annotations

from app.services.admin_client.intent_priority import should_route_users


def test_should_route_users_list():
    assert should_route_users("liste les utilisateurs")


def test_should_route_users_suspend():
    assert should_route_users("suspend le compte #2")


def test_should_not_route_dashboard_kpi():
    assert not should_route_users("répartition des utilisateurs par rôle")


def test_should_not_route_tracking():
    assert not should_route_users("suivi 817725683025")


def test_should_route_users_hash_in_context():
    hist = "Utilisateurs (15)\n| 1 | Bob | bob@test.com |"
    assert should_route_users("télécharge le #1", history_text=hist) or should_route_users(
        "détail du #1", history_text=hist
    )
