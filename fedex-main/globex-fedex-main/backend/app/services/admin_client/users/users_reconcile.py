"""Reconcile plan utilisateurs — paramètres message + routeur."""

from __future__ import annotations

import re

from app.services.admin_client.users.users_followup import extract_email_from_message, extract_user_ref
from app.services.admin_client.users.users_intent import _extract_new_name, _extract_role_filter, _extract_status_filter
from app.services.admin_client.users.users_types import UsersPlan, UsersProfile, UsersTaskType
from app.services.admin_client.users.users_workspace import normalize_users_text

_SEARCH_STOP = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "et",
        "ou",
        "utilisateur",
        "utilisateurs",
        "user",
        "users",
        "compte",
        "comptes",
        "liste",
        "list",
        "montre",
        "affiche",
        "donne",
        "moi",
        "tous",
        "all",
        "suspend",
        "suspendre",
        "supprimer",
        "logs",
        "permissions",
        "detail",
        "fiche",
        "mot",
        "passe",
        "password",
        "reset",
        "je",
        "veux",
    }
)

_PROFILE_FOR_TASK = {
    UsersTaskType.user_list: UsersProfile.LIST,
    UsersTaskType.user_detail: UsersProfile.DETAIL,
    UsersTaskType.user_logs: UsersProfile.LOGS,
    UsersTaskType.user_permissions: UsersProfile.PERMISSIONS,
    UsersTaskType.user_suspend: UsersProfile.CONFIRM,
    UsersTaskType.user_reactivate: UsersProfile.CONFIRM,
    UsersTaskType.user_delete: UsersProfile.CONFIRM,
    UsersTaskType.user_update_name: UsersProfile.CONFIRM,
    UsersTaskType.user_reset_password: UsersProfile.CONFIRM,
}


def _extract_search_query(text: str) -> str | None:
    norm = normalize_users_text(text)
    tokens = [t for t in re.findall(r"[a-z0-9@._-]+", norm) if t not in _SEARCH_STOP and len(t) > 2]
    if not tokens:
        return None
    if "@" in tokens[0]:
        return tokens[0]
    if len(tokens) >= 2:
        return " ".join(tokens[:3])
    return tokens[0]


def reconcile_users_plan(message: str, plan: UsersPlan, *, history_text: str = "") -> UsersPlan:
    text = normalize_users_text(message)

    uid = plan.user_id or extract_user_ref(message, history_text=history_text)
    if uid:
        plan.user_id = uid

    email = extract_email_from_message(message)
    if email and not plan.search_query:
        plan.search_query = email

    if not plan.role_filter:
        plan.role_filter = _extract_role_filter(text)
    if not plan.status_filter:
        plan.status_filter = _extract_status_filter(text)

    if plan.task_type == UsersTaskType.user_list and not plan.search_query:
        if not plan.sort_by and not plan.status_filter and not plan.list_variant:
            plan.search_query = _extract_search_query(text)
    elif plan.task_type != UsersTaskType.user_list:
        if not email:
            plan.search_query = None

    if plan.task_type == UsersTaskType.user_update_name and not plan.new_name:
        plan.new_name = _extract_new_name(message)

    if plan.task_type in _PROFILE_FOR_TASK:
        plan.profile = _PROFILE_FOR_TASK[plan.task_type]

    return plan
