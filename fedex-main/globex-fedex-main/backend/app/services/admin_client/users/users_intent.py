"""Classification intents gestion utilisateurs admin."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.users.users_entity_memory import (
    is_pronoun_user_reference,
    resolve_pronoun_or_context,
)
from app.services.admin_client.users.users_followup import (
    extract_email_from_message,
    extract_user_ref,
    is_users_followup_message,
    is_users_history_context,
    list_user_ids_from_history,
)
from app.services.admin_client.users.users_service import search_users_by_query
from app.services.admin_client.users.users_types import UsersPlan, UsersProfile, UsersTaskType
from app.services.admin_client.users.users_workspace import (
    is_users_workspace,
    normalize_users_text,
    score_users_soft,
)

_LIST_RE = re.compile(
    r"\b("
    r"liste.{0,30}(utilisateurs?|users?|comptes?)|"
    r"list.{0,30}(utilisateurs?|users?|comptes?)|"
    r"(tous les|all)\s+(les\s+)?(utilisateurs?|users?|comptes?)|"
    r"liste\s+(des\s+)?utilisateurs?|list\s+users?|"
    r"montre.{0,20}(utilisateurs?|users?|comptes?)|"
    r"affiche.{0,20}(utilisateurs?|users?|comptes?)"
    r")\b",
    re.I,
)
_DETAIL_RE = re.compile(
    r"\b(fiche|d[eé]tail|infos?|profil|voir).{0,25}(utilisateur|user|compte)\b",
    re.I,
)
_LOGS_RE = re.compile(
    r"\b(logs?|journaux?|historique\s+d.?activit[eé]).{0,25}(utilisateur|user|compte)?\b",
    re.I,
)
_PERMISSIONS_RE = re.compile(
    r"\b(permissions?|quotas?|droits?|acc[eè]s).{0,25}(utilisateur|user|compte)?\b",
    re.I,
)
_SUSPEND_RE = re.compile(r"\b(suspend(?:re|ez)?|bloqu(?:er|ez))\b", re.I)
_REACTIVATE_RE = re.compile(
    r"\b(r[eé]?activ(?:er|ez|e)?|reactive|reactiver|r[eé]active|d[eé]bloqu(?:er|ez))\b",
    re.I,
)
_DELETE_RE = re.compile(r"\b(supprim(?:er|ez)?|delete)\s+.{0,20}(utilisateur|user|compte)?\b", re.I)
_RENAME_RE = re.compile(
    r"\b(renomm(?:er|ez)?|changer\s+le\s+nom|rename)\b",
    re.I,
)
_RESET_PW_RE = re.compile(
    r"\b(reset|mot\s+de\s+passe|r[eé]initialis(?:er|ez)?)\b",
    re.I,
)
_ROLE_RE = re.compile(
    r"\b(clients?|employ[eé]s?|employees?|admins?|administrateurs?)\b",
    re.I,
)
_STATUS_RE = re.compile(
    r"\b(actifs?|suspendu[eé]?s?|suspended|pending|invit[eé]s?|en\s+attente)\b",
    re.I,
)
_BARE_USERS_RE = re.compile(r"^\s*users?\s*$", re.I)
_GIVE_USER_RE = re.compile(
    r"\b(donne|donne-moi|montre|affiche|liste|list|show)\b.{0,40}\b(utilisateurs?|users?|comptes?)\b",
    re.I,
)
_RECENT_CONNECT_RE = re.compile(
    r"\b("
    r"(recem+ent|r[eé]cemment|recent|dernier|last).{0,30}"
    r"(con+n?ect\w*|conn\w+|login|actif|activit[eé]|online)"
    r"|"
    r"(con+n?ect\w*|conn\w+).{0,20}(recem+ent|r[eé]cemment|recent)"
    r"|"
    r"(qui\s+a|who\s+has).{0,25}(con+n?ect\w*|conn\w+|login)"
    r")\b",
    re.I,
)
_ONLINE_NOW_RE = re.compile(r"\b(en\s+ligne|online\s+now|connect[eé]s?\s+maintenant)\b", re.I)
_SUSPEND_LIST_RE = re.compile(
    r"\b("
    r"utilisateurs?\s+suspendu[eé]?s?|comptes?\s+suspendu[eé]?s?|users?\s+suspended|"
    r"suspendu[eé]?s?\s+(utilisateurs?|comptes?|users?)|"
    r"liste.{0,25}suspendu"
    r")\b",
    re.I,
)
_EVER_SUSPENDED_RE = re.compile(
    r"\b("
    r"suspendu[eé]?\s+une\s+fois|"
    r"[eé]tait\s+suspendu|"
    r"[eé]t[eé]\s+suspendu|"
    r"d[eé]j[aà]\s+suspendu|"
    r"was\s+suspended"
    r")\b",
    re.I,
)
_ACTIVITY_LIST_RE = re.compile(
    r"\b("
    r"machine|appareil|depuis\s+quel|"
    r"quand.*connect|connect.*quand|"
    r"chaque\s+utilisateur|"
    r"derni[eè]re\s+(activit[eé]|connexion)|"
    r"last\s+(activity|login|location)"
    r")\b",
    re.I,
)
_NEW_NAME_RE = re.compile(
    r"\b(?:en|vers|to|as)\s+[\"']?([^\"']{2,80})[\"']?\s*$",
    re.I,
)

_PROFILE_FOR_TASK = {
    UsersTaskType.user_list: UsersProfile.LIST,
    UsersTaskType.user_detail: UsersProfile.DETAIL,
    UsersTaskType.user_logs: UsersProfile.LOGS,
    UsersTaskType.user_permissions: UsersProfile.PERMISSIONS,
}

_RESOLVE_STOP = frozenset(
    {
        "utilisateur",
        "utilisateurs",
        "user",
        "users",
        "compte",
        "comptes",
        "suspend",
        "suspendre",
        "supprimer",
        "logs",
        "permissions",
        "detail",
        "fiche",
        "veux",
        "donne",
        "moi",
        "qui",
        "etait",
        "ete",
        "etais",
        "cet",
        "cette",
        "celui",
        "celle",
        "reactiver",
        "reactiv",
        "reactive",
        "chaque",
        "machine",
        "depuis",
        "quand",
        "avec",
        "dans",
        "tous",
        "toutes",
        "liste",
        "list",
    }
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _extract_sort_by(text: str) -> str | None:
    if _ONLINE_NOW_RE.search(text):
        return "online"
    if _RECENT_CONNECT_RE.search(text):
        return "last_activity"
    return None


def _apply_pdf_flag(plan: UsersPlan, message: str) -> UsersPlan:
    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if wants_pdf_format(message):
        plan.want_pdf = True
    return plan


def _build_list_plan(text: str, *, raw: str) -> UsersPlan:
    list_variant: str | None = None
    sort_by = _extract_sort_by(text)
    status_filter = _extract_status_filter(text)

    if _EVER_SUSPENDED_RE.search(text):
        list_variant = "ever_suspended"
        status_filter = None
        sort_by = None
    elif _ACTIVITY_LIST_RE.search(text) or (
        sort_by == "last_activity" and re.search(r"\b(machine|appareil|depuis)\b", text, re.I)
    ):
        list_variant = "activity"
        sort_by = sort_by or "last_activity"
    elif _ACTIVITY_LIST_RE.search(text):
        list_variant = "activity"
        sort_by = sort_by or "last_activity"

    plan = UsersPlan(
        task_type=UsersTaskType.user_list,
        profile=UsersProfile.LIST,
        role_filter=_extract_role_filter(text),
        status_filter=status_filter,
        sort_by=sort_by,
        list_variant=list_variant,
        raw_matches=[raw],
    )
    if _SUSPEND_LIST_RE.search(text) and list_variant != "ever_suspended":
        plan.status_filter = "suspended"
    if plan.sort_by or plan.status_filter or plan.list_variant:
        plan.search_query = None
    return plan


def _extract_role_filter(text: str) -> str | None:
    m = _ROLE_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token in {"client", "clients"}:
        return "client"
    if token in {"employe", "employé", "employes", "employés", "employee", "employees"}:
        return "employe"
    if token in {"admin", "admins", "administrateur", "administrateurs"}:
        return "admin"
    return None


def _extract_status_filter(text: str) -> str | None:
    m = _STATUS_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token in {"actif", "actifs", "active"}:
        return "active"
    if token in {"suspendu", "suspendus", "suspendue", "suspendues", "suspended"}:
        return "suspended"
    if token in {"pending", "en attente"}:
        return "pending"
    if token in {"invité", "invités", "invited"}:
        return "invited"
    return None


def _extract_new_name(message: str) -> str | None:
    m = _NEW_NAME_RE.search(message or "")
    if m:
        return m.group(1).strip()
    m = re.search(r"renomm(?:er|ez)?\s+.+?\s+(?:en|vers)\s+(.+)$", message or "", re.I)
    if m:
        return m.group(1).strip().strip("\"'")
    return None


def default_clarify_question(lang: str) -> str:
    if lang == "en":
        return (
            "Would you like to list users, view a profile, check logs, permissions, "
            "or perform an action (suspend, reactivate, delete, rename, reset password)?"
        )
    return (
        "Voulez-vous lister les utilisateurs, consulter une fiche, les logs, les permissions, "
        "ou effectuer une action (suspendre, réactiver, supprimer, renommer, réinitialiser le MDP) ?"
    )


def clarify_plan_from_router(data: dict[str, Any]) -> UsersPlan:
    question = str(data.get("clarification_question") or "").strip()
    return UsersPlan(
        task_type=UsersTaskType.ambiguous,
        profile=UsersProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=question,
        raw_matches=["router_clarify"],
    )


def default_clarify_plan(lang: str) -> UsersPlan:
    return UsersPlan(
        task_type=UsersTaskType.ambiguous,
        profile=UsersProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=default_clarify_question(lang),
        raw_matches=["default_clarify"],
    )


def plan_from_router_data(data: dict[str, Any]) -> UsersPlan | None:
    task_raw = str(data.get("task_type") or "ambiguous").strip()
    try:
        task = UsersTaskType(task_raw)
    except ValueError:
        task = UsersTaskType.ambiguous
    if task == UsersTaskType.ambiguous:
        return None

    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    user_id = answers.get("user_id")
    try:
        uid = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        uid = None

    profile = _PROFILE_FOR_TASK.get(task, UsersProfile.LIST)
    if task in {
        UsersTaskType.user_suspend,
        UsersTaskType.user_reactivate,
        UsersTaskType.user_delete,
        UsersTaskType.user_update_name,
        UsersTaskType.user_reset_password,
    }:
        profile = UsersProfile.CONFIRM

    return UsersPlan(
        task_type=task,
        user_id=uid,
        role_filter=str(answers.get("role_filter") or "").strip() or None,
        status_filter=str(answers.get("status_filter") or "").strip() or None,
        search_query=str(answers.get("search_query") or "").strip() or None,
        new_name=str(answers.get("new_name") or "").strip() or None,
        suspend_reason=str(answers.get("suspend_reason") or "").strip(),
        limit=min(max(int(answers.get("limit") or 15), 1), 50),
        profile=profile,
        raw_matches=["router"],
    )


def _extract_suspend_reason_from_message(message: str) -> str:
    m = re.search(
        r"\b(?:suspend(?:re|ez)?|bloqu(?:er|ez)?)\b.+?\b(?:pour|motif|raison|because)\s+(.+?)"
        r"(?:\s+et\s+(?:envoie|envoyer|notifie|notifier|pr[eé]venir|mail|e-mail|email)|$)",
        message or "",
        re.I | re.DOTALL,
    )
    if m:
        return m.group(1).strip()[:500]
    return ""


def classify_users_intent(message: str, *, history_text: str = "") -> UsersPlan:
    text = _normalize(message)
    hist = history_text or ""

    from app.services.admin_client.email.email_followup import (
        is_email_clarify_followup,
        recover_suspend_combo_from_history,
    )

    if is_email_clarify_followup(message, history_text=hist):
        recovered = recover_suspend_combo_from_history(hist, message)
        if recovered:
            return _apply_pdf_flag(
                UsersPlan(
                    task_type=UsersTaskType.user_suspend,
                    profile=UsersProfile.CONFIRM,
                    notify_email=True,
                    suspend_reason=recovered.get("suspend_reason", ""),
                    search_query=recovered.get("recipient_email"),
                    raw_matches=["recover_suspend_email_clarify"],
                ),
                message,
            )

    def _apply_notify_email(plan: UsersPlan) -> UsersPlan:
        from app.services.admin_client.email.email_action_offer import wants_notify_user_by_email

        if plan.task_type in {UsersTaskType.user_suspend, UsersTaskType.user_reactivate}:
            if wants_notify_user_by_email(message):
                plan.notify_email = True
        return plan

    def _finish(plan: UsersPlan) -> UsersPlan:
        return _apply_pdf_flag(_apply_notify_email(plan), message)

    if is_users_followup_message(text, history_text=hist) and not _LIST_RE.search(text):
        if _SUSPEND_RE.search(text):
            return _finish(
                UsersPlan(
                    task_type=UsersTaskType.user_suspend,
                    profile=UsersProfile.CONFIRM,
                    suspend_reason=_extract_suspend_reason_from_message(message),
                    raw_matches=["followup_suspend"],
                )
            )
        if _REACTIVATE_RE.search(text):
            return _finish(UsersPlan(task_type=UsersTaskType.user_reactivate, profile=UsersProfile.CONFIRM, raw_matches=["followup_reactivate"]))
        if _DELETE_RE.search(text):
            return _finish(UsersPlan(task_type=UsersTaskType.user_delete, profile=UsersProfile.CONFIRM, raw_matches=["followup_delete"]))
        if _RESET_PW_RE.search(text):
            return _finish(UsersPlan(task_type=UsersTaskType.user_reset_password, profile=UsersProfile.CONFIRM, raw_matches=["followup_reset"]))
        if _RENAME_RE.search(text):
            return _finish(UsersPlan(
                task_type=UsersTaskType.user_update_name,
                profile=UsersProfile.CONFIRM,
                new_name=_extract_new_name(message),
                raw_matches=["followup_rename"],
            ))
        if _LOGS_RE.search(text):
            return _finish(UsersPlan(task_type=UsersTaskType.user_logs, profile=UsersProfile.LOGS, raw_matches=["followup_logs"]))
        if _PERMISSIONS_RE.search(text):
            return _finish(UsersPlan(task_type=UsersTaskType.user_permissions, profile=UsersProfile.PERMISSIONS, raw_matches=["followup_permissions"]))
        return _finish(UsersPlan(task_type=UsersTaskType.user_detail, profile=UsersProfile.DETAIL, raw_matches=["followup_detail"]))

    if _SUSPEND_RE.search(text):
        return _finish(
            UsersPlan(
                task_type=UsersTaskType.user_suspend,
                profile=UsersProfile.CONFIRM,
                suspend_reason=_extract_suspend_reason_from_message(message),
                raw_matches=["suspend"],
            )
        )
    if _REACTIVATE_RE.search(text):
        return _finish(UsersPlan(task_type=UsersTaskType.user_reactivate, profile=UsersProfile.CONFIRM, raw_matches=["reactivate"]))
    if _DELETE_RE.search(text):
        return _finish(UsersPlan(task_type=UsersTaskType.user_delete, profile=UsersProfile.CONFIRM, raw_matches=["delete"]))
    if _RESET_PW_RE.search(text):
        return _finish(UsersPlan(task_type=UsersTaskType.user_reset_password, profile=UsersProfile.CONFIRM, raw_matches=["reset_password"]))
    if _RENAME_RE.search(text):
        return _finish(UsersPlan(
            task_type=UsersTaskType.user_update_name,
            profile=UsersProfile.CONFIRM,
            new_name=_extract_new_name(message),
            raw_matches=["rename"],
        ))
    if _LOGS_RE.search(text):
        return _finish(UsersPlan(task_type=UsersTaskType.user_logs, profile=UsersProfile.LOGS, raw_matches=["logs"]))
    if _PERMISSIONS_RE.search(text):
        return _finish(UsersPlan(task_type=UsersTaskType.user_permissions, profile=UsersProfile.PERMISSIONS, raw_matches=["permissions"]))
    if _DETAIL_RE.search(text) or extract_email_from_message(text):
        return _finish(UsersPlan(task_type=UsersTaskType.user_detail, profile=UsersProfile.DETAIL, raw_matches=["detail"]))
    if _EVER_SUSPENDED_RE.search(text):
        return _finish(_build_list_plan(text, raw="ever_suspended"))
    if _ACTIVITY_LIST_RE.search(text):
        return _finish(_build_list_plan(text, raw="activity_list"))
    if _RECENT_CONNECT_RE.search(text) and re.search(
        r"\b(user|utilisateur|compte)\b", text, re.I
    ):
        return _finish(_build_list_plan(text, raw="recent_connect"))
    if _LIST_RE.search(text) or _BARE_USERS_RE.search(text):
        return _finish(_build_list_plan(text, raw="list"))
    if _GIVE_USER_RE.search(text):
        return _finish(_build_list_plan(text, raw="give_list"))

    if is_users_workspace(text, history_text=hist):
        if score_users_soft(text) < 2.5 or _RECENT_CONNECT_RE.search(text) or _SUSPEND_LIST_RE.search(text):
            plan = _build_list_plan(text, raw="workspace_list") if (
                _GIVE_USER_RE.search(text) or _RECENT_CONNECT_RE.search(text) or _SUSPEND_LIST_RE.search(text)
            ) else UsersPlan(task_type=UsersTaskType.ambiguous, needs_router=True, raw_matches=["grey_zone"])
            if plan.task_type == UsersTaskType.ambiguous:
                return _finish(plan)
            return _finish(plan)
        return _finish(UsersPlan(task_type=UsersTaskType.user_list, profile=UsersProfile.LIST, raw_matches=["workspace_default"]))

    return _finish(UsersPlan(task_type=UsersTaskType.ambiguous, raw_matches=["no_match"]))


@dataclass
class TargetUserResolution:
    user_id: int | None = None
    needs_clarification: bool = False
    clarification_question: str = ""
    candidates: list[dict[str, str]] | None = None


def resolve_target_user(
    db: Session,
    message: str,
    plan: UsersPlan,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> TargetUserResolution:
    if plan.user_id:
        return TargetUserResolution(user_id=plan.user_id)

    text = message or ""
    ref = extract_user_ref(text, history_text=history_text)
    if ref is not None:
        return TargetUserResolution(user_id=ref)

    email = extract_email_from_message(text)
    if email:
        user = db.scalars(select(User).where(User.email.ilike(email)).limit(1)).first()
        if user:
            return TargetUserResolution(user_id=user.id)
        return TargetUserResolution(
            needs_clarification=True,
            clarification_question=(
                f"Aucun utilisateur avec l'e-mail **{email}**."
                if lang == "fr"
                else f"No user found with email **{email}**."
            ),
        )

    if is_users_history_context(history_text):
        m = re.search(r"\b(?:le|la)\s+(\d{1,3})\b", text, re.I)
        if m:
            idx = int(m.group(1)) - 1
            ids = list_user_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return TargetUserResolution(user_id=ids[idx])

    if is_pronoun_user_reference(text) or (
        not extract_email_from_message(text)
        and plan.task_type
        in {
            UsersTaskType.user_detail,
            UsersTaskType.user_logs,
            UsersTaskType.user_permissions,
            UsersTaskType.user_suspend,
            UsersTaskType.user_reactivate,
            UsersTaskType.user_delete,
            UsersTaskType.user_update_name,
            UsersTaskType.user_reset_password,
        }
    ):
        uid_ctx, email_ctx = resolve_pronoun_or_context(text, history_text)
        if uid_ctx:
            return TargetUserResolution(user_id=uid_ctx)
        if email_ctx:
            user = db.scalars(select(User).where(User.email.ilike(email_ctx)).limit(1)).first()
            if user:
                return TargetUserResolution(user_id=user.id)

    if plan.search_query and plan.task_type == UsersTaskType.user_list:
        return TargetUserResolution()

    q = (plan.search_query or "").strip()
    if not q and plan.task_type != UsersTaskType.user_list:
        tokens = [
            t
            for t in re.findall(r"[a-zA-Z0-9@._-]+", normalize_users_text(text))
            if len(t) > 2 and t not in _RESOLVE_STOP
        ]
        for tok in tokens:
            if "@" in tok or (len(tok) >= 4 and tok.isalpha()):
                q = tok
                break

    if not q:
        if plan.task_type in {
            UsersTaskType.user_detail,
            UsersTaskType.user_logs,
            UsersTaskType.user_permissions,
            UsersTaskType.user_suspend,
            UsersTaskType.user_reactivate,
            UsersTaskType.user_delete,
            UsersTaskType.user_update_name,
            UsersTaskType.user_reset_password,
        }:
            return TargetUserResolution(
                needs_clarification=True,
                clarification_question=(
                    "Quel utilisateur ciblez-vous (e-mail, #id ou numéro dans la liste) ?"
                    if lang == "fr"
                    else "Which user do you mean (email, #id, or list number)?"
                ),
            )
        return TargetUserResolution()

    matches = search_users_by_query(db, q, limit=5)
    if len(matches) == 1:
        return TargetUserResolution(user_id=matches[0].id)
    if len(matches) > 1:
        candidates = [
            {"id": str(u.id), "email": u.email, "full_name": u.full_name or ""} for u in matches
        ]
        lines = ", ".join(f"#{u.id} {u.email}" for u in matches[:5])
        return TargetUserResolution(
            needs_clarification=True,
            clarification_question=(
                f"Plusieurs utilisateurs correspondent : {lines}. Précisez l'e-mail ou #id."
                if lang == "fr"
                else f"Multiple users match: {lines}. Please specify email or #id."
            ),
            candidates=candidates,
        )
    return TargetUserResolution(
        needs_clarification=True,
        clarification_question=(
            f"Aucun utilisateur trouvé pour « {q} »."
            if lang == "fr"
            else f"No user found for « {q} »."
        ),
    )
