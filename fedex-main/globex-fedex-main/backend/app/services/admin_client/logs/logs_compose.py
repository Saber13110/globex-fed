"""Réponses déterministes journaux d'activité admin."""

from __future__ import annotations

import json
from typing import Any

from app.services.admin_client.logs.logs_pending import (
    LOGS_CONFIRM_MARKER_EN,
    LOGS_CONFIRM_MARKER_FR,
    build_logs_pending_marker,
)
from app.services.admin_client.logs.logs_types import LogsPlan, LogsProfile, LogsTaskType


def compose_logs_response(
    processed: dict[str, Any],
    plan: LogsPlan,
    *,
    lang: str = "fr",
    error_code: str | None = None,
    action_result: dict[str, Any] | None = None,
) -> str:
    if error_code:
        return _error_text(error_code, lang)
    if plan.profile == LogsProfile.LIST:
        return _compose_list(processed, plan, lang)
    if plan.profile == LogsProfile.DETAIL:
        return _compose_detail(processed, lang)
    if plan.profile == LogsProfile.SUMMARY:
        return _compose_summary(processed, lang)
    if plan.profile == LogsProfile.ANOMALIES:
        return _compose_anomalies(processed, lang)
    if plan.profile == LogsProfile.CONVERSATION:
        return _compose_conversation(processed, lang)
    if plan.profile == LogsProfile.CONFIRM:
        return _compose_confirm(processed, plan, lang)
    if plan.profile == LogsProfile.DONE:
        return _compose_done(processed, action_result or {}, lang)
    if plan.profile == LogsProfile.CLARIFY:
        return plan.clarification_question or default_clarify(lang)
    return _compose_list(processed, plan, lang)


def default_clarify(lang: str) -> str:
    if lang == "en":
        return "Could you clarify your activity logs request?"
    return "Pouvez-vous préciser votre demande sur les journaux d'activité ?"


def _error_text(code: str, lang: str) -> str:
    catalog_fr = {
        "log_not_found": "Entrée de journal introuvable.",
        "fetch_failed": "Impossible de récupérer les journaux en temps réel.",
        "user_not_found": "Utilisateur introuvable.",
        "no_conversation": "Aucune conversation liée à ce log.",
        "cannot_suspend_admin": "Impossible de suspendre un administrateur.",
        "already_suspended": "Compte déjà suspendu.",
    }
    catalog_en = {
        "log_not_found": "Log entry not found.",
        "fetch_failed": "Could not fetch live log data.",
        "user_not_found": "User not found.",
        "no_conversation": "No conversation linked to this log.",
        "cannot_suspend_admin": "Cannot suspend an administrator.",
        "already_suspended": "Account already suspended.",
    }
    catalog = catalog_en if lang == "en" else catalog_fr
    label = "Erreur" if lang == "fr" else "Error"
    return f"**{label}** — {catalog.get(code, code)}"


def _filter_bits(plan: LogsPlan, lang: str) -> list[str]:
    bits: list[str] = []
    if plan.level_filter:
        bits.append(f"niveau={plan.level_filter}")
    if plan.category_filter:
        bits.append(f"catégorie={plan.category_filter}" if lang == "fr" else f"category={plan.category_filter}")
    if plan.action_filter:
        bits.append(f"action={plan.action_filter}")
    if plan.period_hours:
        bits.append(f"{plan.period_hours}h")
    if plan.since_today:
        bits.append("aujourd'hui" if lang == "fr" else "today")
    if plan.search_query:
        bits.append(f"q={plan.search_query}")
    return bits


def _escape_cell(value: str) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")[:80]


def _compose_list(processed: dict[str, Any], plan: LogsPlan, lang: str) -> str:
    logs = processed.get("logs") or []
    title = "**Journal d'activité**" if lang == "fr" else "**Activity log**"
    filter_bits = _filter_bits(plan, lang)
    header = title + (f" ({', '.join(filter_bits)})" if filter_bits else "")

    if not logs:
        empty = (
            "Aucune entrée ne correspond aux filtres."
            if lang == "fr"
            else "No entries match the filters."
        )
        return f"{header}\n\n{empty}"

    lines = [
        header,
        "",
        f"{'Affichés' if lang == 'fr' else 'Shown'} : **{len(logs)}** / {processed.get('total', len(logs))}",
        "",
        "| # | Date | Niveau | Action | Utilisateur | Message |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in logs:
        created = str(row.get("created_at", ""))[:19]
        user = row.get("user_email") or row.get("actor_email") or "—"
        msg = _escape_cell(str(row.get("message") or "—")[:100])
        lines.append(
            f"| {row.get('id')} | {created} | {row.get('level', '—')} | "
            f"`{row.get('action', '—')}` | {user} | {msg} |"
        )
    hint = (
        "\n\n_Indice : #id ou « le N » pour le détail / conversation._"
        if lang == "fr"
        else "\n\n_Tip: use #id or row N for detail / conversation._"
    )
    return "\n".join(lines) + hint


def _compose_detail(processed: dict[str, Any], lang: str) -> str:
    row = processed.get("log") or {}
    title = "**Fiche log**" if lang == "fr" else "**Log detail**"
    meta = row.get("metadata") or {}
    try:
        if not meta and row.get("metadata_json"):
            meta = json.loads(row.get("metadata_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}
    lines = [
        title,
        "",
        f"**#{row.get('id')}** — `{row.get('action', '—')}`",
        f"Niveau : **{row.get('level', '—')}** | Catégorie : {row.get('category', '—')}",
        f"Date : {str(row.get('created_at', ''))[:19]} | IP : {row.get('ip_address') or '—'}",
        f"Utilisateur : {row.get('user_name', '—')} ({row.get('user_email') or '—'})",
        f"Acteur : {row.get('actor_email') or '—'}",
        "",
        f"**Message** : {(row.get('message') or '—')[:800]}",
    ]
    if meta:
        lines.extend(["", "**Métadonnées** :", f"```json\n{json.dumps(meta, ensure_ascii=False, indent=2)[:1200]}\n```"])
    sid = processed.get("session_id")
    if sid:
        lines.append(
            f"\n_Conversation liée : session **#{sid}** — demandez « ouvre la conversation de ce log »._"
            if lang == "fr"
            else f"\n_Linked conversation: session **#{sid}** — ask to open it._"
        )
    return "\n".join(lines)


def _compose_summary(processed: dict[str, Any], lang: str) -> str:
    s = processed.get("summary") or processed
    if s.get("platform"):
        title = (
            "**Résumé activité plateforme (aujourd'hui)**"
            if lang == "fr"
            else "**Platform activity summary (today)**"
        )
        lines = [
            title,
            "",
            f"**Total** : {s.get('total', 0)} événements"
            if lang == "fr"
            else f"**Total** : {s.get('total', 0)} events",
            f"**Utilisateurs actifs** : {s.get('active_users', 0)}"
            if lang == "fr"
            else f"**Active users** : {s.get('active_users', 0)}",
        ]
    else:
        title = (
            f"**Résumé activité — {s.get('user_name', '—')} ({s.get('user_email', '—')})**"
            if lang == "fr"
            else f"**Activity summary — {s.get('user_name', '—')} ({s.get('user_email', '—')})**"
        )
        lines = [
            title,
            "",
            f"**Total** : {s.get('total', 0)} événements"
            if lang == "fr"
            else f"**Total** : {s.get('total', 0)} events",
        ]
    if s.get("by_level"):
        lines.append(f"**Niveaux** : {', '.join(f'{k}: {v}' for k, v in s['by_level'].items())}")
    if s.get("by_category"):
        lines.append(f"**Catégories** : {', '.join(f'{k}: {v}' for k, v in list(s['by_category'].items())[:6])}")
    if s.get("by_action"):
        lines.append("**Actions fréquentes** :" if lang == "fr" else "**Top actions**:")
        for act, cnt in list(s.get("by_action", {}).items())[:6]:
            lines.append(f"- `{act}` : {cnt}")
    for row in (s.get("warnings") or [])[:3]:
        lines.append(f"- ⚠ `{row.get('action')}` — {(row.get('message') or '')[:80]}")
    for row in (s.get("errors") or [])[:3]:
        lines.append(f"- ❌ `{row.get('action')}` — {(row.get('message') or '')[:80]}")
    return "\n".join(lines)


def _compose_anomalies(processed: dict[str, Any], lang: str) -> str:
    a = processed.get("analysis") or processed
    title = "**Analyse sécurité des logs**" if lang == "fr" else "**Security log analysis**"
    lines = [
        title,
        "",
        f"**Risque** : {str(a.get('risk_level', '—')).upper()}",
        f"**Période** : {a.get('period_hours', 24)}h | **Logs analysés** : {a.get('total_logs', 0)}",
        f"Échecs login : {a.get('login_failures', 0)} | Injections : {a.get('injection_attempts', 0)}",
        "",
        "**Événements suspects** :" if lang == "fr" else "**Suspicious events**:",
    ]
    events = a.get("suspicious_events") or []
    if not events:
        lines.append("_Aucun événement suspect détecté._" if lang == "fr" else "_No suspicious events detected._")
    else:
        for ev in events[:12]:
            lines.append(f"- [{ev.get('type', '—')}] {ev.get('detail', '—')}")
    return "\n".join(lines)


def _compose_conversation(processed: dict[str, Any], lang: str) -> str:
    conv = processed.get("conversation") or {}
    log = processed.get("log") or {}
    title = "**Conversation liée au log**" if lang == "fr" else "**Conversation linked to log**"
    lines = [
        title,
        "",
        f"Log **#{log.get('id', '—')}** → Session **#{conv.get('session_id') or conv.get('id', '—')}**",
        f"**{conv.get('title', '—')}** — {conv.get('user_name', '—')} ({conv.get('user_email', '—')})",
        "",
    ]
    messages = conv.get("messages") or []
    if not messages:
        lines.append("_Aucun message._" if lang == "fr" else "_No messages._")
    else:
        lines.append("**Fil** :" if lang == "fr" else "**Thread**:")
        for m in messages[-15:]:
            sender = m.get("sender") or m.get("role") or "—"
            body = (m.get("message_text") or m.get("content") or "—").replace("\n", " ")[:200]
            lines.append(f"- _{sender}_ : {body}")
    return "\n".join(lines)


def _compose_confirm(processed: dict[str, Any], plan: LogsPlan, lang: str) -> str:
    log = processed.get("log") or {}
    user = processed.get("user") or {}
    lines = [
        f"**{'Confirmation requise' if lang == 'fr' else 'Confirmation required'}**",
        "",
        "Vous demandez à **suspendre le compte** lié à ce log :"
        if lang == "fr"
        else "You are about to **suspend the account** linked to this log:",
        f"- Log **#{log.get('id')}** — `{log.get('action', '—')}`",
        f"- **#{user.get('id')}** {user.get('full_name', '—')} ({user.get('email', '—')})",
        f"- Statut actuel : **{user.get('status', '—')}**",
    ]
    marker_text = LOGS_CONFIRM_MARKER_FR if lang == "fr" else LOGS_CONFIRM_MARKER_EN
    lines.extend(["", marker_text + "."])
    pending = build_logs_pending_marker(
        "suspend",
        log_id=int(log.get("id") or plan.log_id or 0),
        user_id=int(user.get("id") or plan.user_id or 0),
        payload={"reason": f"Suspension depuis log #{log.get('id')}"},
    )
    return "\n".join(lines) + pending


def _compose_done(processed: dict[str, Any], result: dict[str, Any], lang: str) -> str:
    email = result.get("email") or (processed.get("user") or {}).get("email", "—")
    msg = (
        f"Compte **{email}** suspendu (action depuis le journal d'activité)."
        if lang == "fr"
        else f"Account **{email}** suspended (from activity log action)."
    )
    return f"**{'Action effectuée' if lang == 'fr' else 'Action completed'}**\n\n{msg}"
