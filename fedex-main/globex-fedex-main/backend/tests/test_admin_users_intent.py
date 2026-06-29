"""Tests classification intents utilisateurs admin."""

from __future__ import annotations

from app.services.admin_client.users.users_intent import classify_users_intent
from app.services.admin_client.users.users_reconcile import reconcile_users_plan
from app.services.admin_client.users.users_types import UsersTaskType


def test_intent_list_suspended():
    plan = classify_users_intent("liste les utilisateurs suspendus")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.status_filter == "suspended"


def test_intent_list_suspendue_typo():
    plan = classify_users_intent("liste les utilisateurs suspendue")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.status_filter == "suspended"


def test_intent_recent_connect_typo():
    plan = classify_users_intent("donne moi user qui a recement se connercter")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.sort_by == "last_activity"
    plan = reconcile_users_plan("donne moi user qui a recement se connercter", plan)
    assert plan.search_query is None


def test_intent_ever_suspended_history():
    plan = classify_users_intent("utilisateurs suspendue une fois")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.list_variant == "ever_suspended"
    assert plan.status_filter is None


def test_intent_activity_machine_list():
    plan = classify_users_intent("chaque utilisateur connecté quand et quelle machine")
    assert plan.task_type == UsersTaskType.user_list
    assert plan.list_variant == "activity"


def test_intent_reactivate_no_accent():
    plan = classify_users_intent("reactive ce compte")
    assert plan.task_type == UsersTaskType.user_reactivate


def test_intent_suspend():
    plan = classify_users_intent("suspend le compte bob@test.com")
    assert plan.task_type == UsersTaskType.user_suspend


def test_intent_user_hash():
    plan = classify_users_intent("logs de l'utilisateur #5")
    assert plan.task_type == UsersTaskType.user_logs


def test_intent_followup_after_list():
    hist = "Liste des utilisateurs\n| 1 | Bob | bob@test.com | client | active |"
    plan = classify_users_intent("le 2", history_text=hist)
    assert plan.task_type in {UsersTaskType.user_detail, UsersTaskType.user_logs}
