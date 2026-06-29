"""Tests mémoire entité et listes sémantiques utilisateurs."""

from __future__ import annotations

from app.services.admin_client.users.users_entity_memory import (
    extract_focus_user_from_history,
    is_pronoun_user_reference,
    resolve_pronoun_or_context,
)
from app.services.admin_client.users.users_intent import classify_users_intent
from app.services.admin_client.users.users_types import UsersTaskType


def test_focus_user_from_logs_header():
    hist = "**Logs — #5 amine@gmail.com**\n- event"
    uid, email = extract_focus_user_from_history(hist)
    assert uid == 5
    assert email == "amine@gmail.com"


def test_focus_user_from_done_suspend():
    hist = (
        "**Action effectuée**\n\n"
        "Compte **bob@test.com** suspendu."
    )
    uid, email = extract_focus_user_from_history(hist)
    assert uid is None
    assert email == "bob@test.com"


def test_pronoun_ce_compte():
    assert is_pronoun_user_reference("reactive ce compte")


def test_resolve_reactivate_after_done():
    hist = "**Action effectuée**\n\nCompte **bob@test.com** suspendu."
    uid, email = resolve_pronoun_or_context("reactive ce compte", hist)
    assert email == "bob@test.com"


def test_pronoun_detection():
    assert is_pronoun_user_reference("je veux suspendre cet utilisateur")


def test_intent_recent_connected_list():
    plan = classify_users_intent("donne moi utilisateur recemment connecte")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.sort_by == "last_activity"
    assert plan.search_query is None


def test_intent_suspended_list_current_status():
    plan = classify_users_intent("donne moi utilisateur suspendu")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.status_filter == "suspended"
