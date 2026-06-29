"""Réponses déterministes gestion utilisateurs admin."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.users.users_pending import (
    USERS_CONFIRM_MARKER_EN,
    USERS_CONFIRM_MARKER_FR,
    build_users_pending_marker,
)
from app.services.admin_client.users.users_types import UsersPlan, UsersProfile, UsersTaskType

_SOURCE_FOOTER_FR = "\n\n_Source : Gestion utilisateurs Admin_"
_SOURCE_FOOTER_EN = "\n\n_Source: Admin User Management_"


def users_source_footer(lang: str) -> str:
    return _SOURCE_FOOTER_EN if lang == "en" else _SOURCE_FOOTER_FR


_ERROR_MESSAGES_FR: dict[str, str] = {
    "user_not_found": "Utilisateur introuvable.",
    "cannot_suspend_admin": "Impossible de suspendre un administrateur.",
    "already_suspended": "Compte déjà suspendu ou action impossible.",
    "reactivate_failed": "Réactivation impossible.",
    "cannot_delete_self": "Impossible de supprimer votre propre compte.",
    "cannot_delete_last_admin": "Impossible de supprimer le dernier administrateur.",
    "invalid_name": "Nom invalide.",
    "smtp_not_configured": "Service e-mail non configuré (vérifiez les variables SMTP_*).",
}

_ERROR_MESSAGES_EN: dict[str, str] = {
    "user_not_found": "User not found.",
    "cannot_suspend_admin": "Cannot suspend an administrator.",
    "already_suspended": "Account already suspended or action not possible.",
    "reactivate_failed": "Reactivation failed.",
    "cannot_delete_self": "Cannot delete your own account.",
    "cannot_delete_last_admin": "Cannot delete the last administrator.",
    "invalid_name": "Invalid name.",
    "smtp_not_configured": "Email service not configured (check SMTP_* variables).",
}


def _error_text(code: str, lang: str) -> str:
    catalog = _ERROR_MESSAGES_EN if lang == "en" else _ERROR_MESSAGES_FR
    if code.startswith("email_send_failed:"):
        detail = code.split(":", 1)[-1]
        if lang == "en":
            return f"Failed to send email: {detail}"
        return f"Échec de l'envoi de l'e-mail : {detail}"
    return catalog.get(code, code)


def compose_users_response(
    processed: dict[str, Any],
    plan: UsersPlan,
    *,
    lang: str = "fr",
    action_result: dict[str, Any] | None = None,
    error_code: str | None = None,
    include_footer: bool = False,
) -> str:
    profile = plan.profile
    if error_code:
        body = f"**{'Erreur' if lang == 'fr' else 'Error'}** — {_error_text(error_code, lang)}"
    elif profile == UsersProfile.LIST:
        body = _compose_list(processed, lang)
    elif profile == UsersProfile.DETAIL:
        body = _compose_detail(processed, lang)
    elif profile == UsersProfile.LOGS:
        body = _compose_logs(processed, lang)
    elif profile == UsersProfile.PERMISSIONS:
        body = _compose_permissions(processed, lang)
    elif profile == UsersProfile.CONFIRM:
        body = _compose_confirm(processed, plan, lang)
    elif profile == UsersProfile.DONE:
        body = _compose_done(processed, plan, action_result or {}, lang)
    elif profile == UsersProfile.CLARIFY:
        body = plan.clarification_question or (
            "Pouvez-vous préciser votre demande concernant les utilisateurs ?"
            if lang == "fr"
            else "Could you clarify your users request?"
        )
    elif profile == UsersProfile.ERROR:
        body = f"**{'Erreur' if lang == 'fr' else 'Error'}** — {processed.get('message', '—')}"
    else:
        body = _compose_list(processed, lang)

    footer = users_source_footer(lang) if include_footer else ""
    return body + footer


def _compose_list(processed: dict[str, Any], lang: str) -> str:
    users = processed.get("users") or []
    title = "**Liste des utilisateurs**" if lang == "fr" else "**User list**"
    if not users:
        empty = "Aucun utilisateur ne correspond aux filtres." if lang == "fr" else "No users match the filters."
        return f"{title}\n\n{empty}"

    filters = processed.get("filters") or {}
    filter_bits = []
    if filters.get("role"):
        filter_bits.append(f"rôle={filters['role']}")
    if filters.get("status"):
        filter_bits.append(f"statut={filters['status']}")
    if filters.get("search"):
        filter_bits.append(f"recherche={filters['search']}")
    if filters.get("sort"):
        filter_bits.append(f"tri={filters['sort']}")
    if filters.get("list_variant") == "ever_suspended":
        filter_bits.append("suspendus au moins une fois" if lang == "fr" else "ever suspended")
    elif filters.get("list_variant") == "activity":
        filter_bits.append("activité récente" if lang == "fr" else "recent activity")
    header = title
    if filter_bits:
        header += f" ({', '.join(filter_bits)})"

    show_activity = (
        filters.get("list_variant") == "activity"
        or filters.get("sort") in {"last_activity", "online"}
    )

    lines = [
        header,
        "",
        f"{'Affichés' if lang == 'fr' else 'Shown'} : **{len(users)}**",
        "",
    ]
    if show_activity:
        lines.extend([
            "| # | Nom | E-mail | Dernière activité | En ligne | Machine |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for u in users:
            last_act = str(u.get("last_activity_at") or "—")[:19]
            online = ("Oui" if lang == "fr" else "Yes") if u.get("is_online") else ("Non" if lang == "fr" else "No")
            machine = _escape_cell(str(u.get("last_location") or "—"))
            lines.append(
                f"| {u.get('id')} | {_escape_cell(str(u.get('full_name', '—')))} | "
                f"{u.get('email', '—')} | {last_act} | {online} | {machine} |"
            )
    else:
        lines.extend([
            "| # | Nom | E-mail | Rôle | Statut |",
            "| --- | --- | --- | --- | --- |",
        ])
        for u in users:
            lines.append(
                f"| {u.get('id')} | {u.get('full_name', '—')} | {u.get('email', '—')} | "
                f"{u.get('role', '—')} | {u.get('status', '—')} |"
            )
    hint = (
        "\n\n_Indice : précisez #id, e-mail ou « le N » pour une action sur une ligne._"
        if lang == "fr"
        else "\n\n_Tip: use #id, email, or « the N » for follow-up actions._"
    )
    return "\n".join(lines) + hint


def _compose_detail(processed: dict[str, Any], lang: str) -> str:
    u = processed.get("user") or {}
    title = "**Fiche utilisateur**" if lang == "fr" else "**User profile**"
    lines = [
        title,
        "",
        f"**#{u.get('id')}** — {u.get('full_name', '—')}",
        f"E-mail : **{u.get('email', '—')}**" if lang == "fr" else f"Email: **{u.get('email', '—')}**",
        f"Rôle : **{u.get('role', '—')}**" if lang == "fr" else f"Role: **{u.get('role', '—')}**",
        f"Statut : **{u.get('status', '—')}**" if lang == "fr" else f"Status: **{u.get('status', '—')}**",
        f"Organisation : {u.get('organization_id', '—')}",
        f"Messages : **{u.get('messages_count', 0)}** | Suivis : **{u.get('trackings_count', 0)}**",
    ]
    if u.get("is_online"):
        lines.append("En ligne" if lang == "fr" else "Online")
    return "\n".join(lines)


def _escape_cell(value: str) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")


def _compose_logs(processed: dict[str, Any], lang: str) -> str:
    u = processed.get("user") or {}
    logs = processed.get("logs") or []
    title = f"**Logs — #{u.get('id')} {u.get('email', '')}**"
    if not logs:
        empty = "Aucun événement trouvé." if lang == "fr" else "No events found."
        return f"{title}\n\n{empty}"
    lines = [title, ""]
    for row in logs[:20]:
        created = str(row.get("created_at", ""))[:19]
        msg = _escape_cell(str(row.get("message") or "—")[:120])
        lines.append(
            f"- **{created}** [{row.get('level', '—')}] `{row.get('action', '—')}` — {msg}"
        )
    total = processed.get("logs_total", len(logs))
    if total > len(logs):
        lines.append(f"\n_… {total - len(logs)} événements supplémentaires._" if lang == "fr" else f"\n_… {total - len(logs)} more events._")
    return "\n".join(lines)


def _compose_permissions(processed: dict[str, Any], lang: str) -> str:
    p = processed.get("permissions") or {}
    title = "**Permissions & quotas**" if lang == "en" else "**Permissions et quotas**"
    lines = [
        title,
        "",
        f"**#{p.get('user_id')}** — {p.get('full_name', '—')} ({p.get('email', '—')})",
        f"Rôle : **{p.get('role', '—')}** | Statut : **{p.get('status', '—')}**",
        f"Organisation : {p.get('organization_id', '—')}",
    ]
    quotas = p.get("quotas") or {}
    if quotas:
        limits = quotas.get("limits") or {}
        usage = quotas.get("usage") or {}
        lines.append("")
        lines.append("**Quotas**" if lang == "fr" else "**Quotas**")
        for key in sorted(limits.keys()):
            lines.append(f"- {key} : {usage.get(key, 0)} / {limits.get(key, '∞')}")
    prefs = (p.get("response_preferences") or "").strip()
    if prefs:
        lines.append(f"\nPréférences réponse : {prefs[:200]}")
    return "\n".join(lines)


def _action_label(task: UsersTaskType, lang: str) -> str:
    labels_fr = {
        UsersTaskType.user_suspend: "suspendre le compte",
        UsersTaskType.user_reactivate: "réactiver le compte",
        UsersTaskType.user_delete: "supprimer le compte",
        UsersTaskType.user_update_name: "renommer l'utilisateur",
        UsersTaskType.user_reset_password: "réinitialiser le mot de passe",
    }
    labels_en = {
        UsersTaskType.user_suspend: "suspend the account",
        UsersTaskType.user_reactivate: "reactivate the account",
        UsersTaskType.user_delete: "delete the account",
        UsersTaskType.user_update_name: "rename the user",
        UsersTaskType.user_reset_password: "reset the password",
    }
    catalog = labels_en if lang == "en" else labels_fr
    return catalog.get(task, task.value)


def _compose_confirm(processed: dict[str, Any], plan: UsersPlan, lang: str) -> str:
    u = processed.get("user") or {}
    action = _action_label(plan.task_type, lang)
    lines = [
        f"**{'Confirmation requise' if lang == 'fr' else 'Confirmation required'}**",
        "",
        f"Vous demandez à **{action}** :" if lang == "fr" else f"You are about to **{action}**:",
        f"- **#{u.get('id')}** {u.get('full_name', '—')}",
        f"- {u.get('email', '—')}",
        f"- Rôle : {u.get('role', '—')} | Statut : {u.get('status', '—')}",
    ]
    if plan.task_type == UsersTaskType.user_update_name and plan.new_name:
        lines.append(f"- Nouveau nom : **{plan.new_name}**")
    marker_text = USERS_CONFIRM_MARKER_FR if lang == "fr" else USERS_CONFIRM_MARKER_EN
    lines.append("")
    lines.append(marker_text + ".")
    payload: dict[str, str] = {}
    if plan.suspend_reason:
        payload["reason"] = plan.suspend_reason
    if plan.new_name:
        payload["new_name"] = plan.new_name
    if plan.notify_email:
        payload["notify_email"] = "true"
    action_key = plan.task_type.value.replace("user_", "")
    pending = build_users_pending_marker(action_key, int(u.get("id") or plan.user_id or 0), payload)
    return "\n".join(lines) + pending


def _compose_done(
    processed: dict[str, Any],
    plan: UsersPlan,
    result: dict[str, Any],
    lang: str,
) -> str:
    email = result.get("email") or (processed.get("user") or {}).get("email", "—")
    msgs_fr = {
        UsersTaskType.user_suspend: f"Compte **{email}** suspendu.",
        UsersTaskType.user_reactivate: f"Compte **{email}** réactivé.",
        UsersTaskType.user_delete: f"Compte **{email}** supprimé.",
        UsersTaskType.user_update_name: f"Nom mis à jour pour **{email}**.",
        UsersTaskType.user_reset_password: f"Mot de passe réinitialisé — e-mail envoyé à **{email}**.",
    }
    msgs_en = {
        UsersTaskType.user_suspend: f"Account **{email}** suspended.",
        UsersTaskType.user_reactivate: f"Account **{email}** reactivated.",
        UsersTaskType.user_delete: f"Account **{email}** deleted.",
        UsersTaskType.user_update_name: f"Name updated for **{email}**.",
        UsersTaskType.user_reset_password: f"Password reset — email sent to **{email}**.",
    }
    catalog = msgs_en if lang == "en" else msgs_fr
    return f"**{'Action effectuée' if lang == 'fr' else 'Action completed'}**\n\n{catalog.get(plan.task_type, 'OK')}"
