"""
Couche obligatoire de formatage final — aucun résultat technique affiché à l'utilisateur.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.ai_assistant.response_sanitizer import (
    format_payload_as_french,
    format_tool_result_for_user as _format_tool_result,
    sanitize_reply,
)

_RAW_TOOL_PREFIX_RE = re.compile(
    r"^(R[eé]sultat\s+\w+\s*:|Result\s+\w+\s*:)\s*",
    re.I,
)


def format_tool_result_for_user(
    result: dict[str, Any] | str | None,
    *,
    intent: str = "",
    language: str = "fr",
    tool_name: str = "",
) -> str:
    """Point d'entrée unique — transforme toute sortie outil en réponse professionnelle."""
    if isinstance(result, str):
        return finalize_reply(result, language=language)

    payload = result or {}
    if tool_name.startswith("export_") or intent.startswith("export_"):
        return _format_tool_result(payload, intent=intent, language=language, tool_name=tool_name)

    if intent == "security_critical_incidents" or "security" in tool_name:
        return format_security_for_user(payload, language=language)

    if intent in {"open_tickets", "tickets"} or "ticket" in tool_name:
        return format_tickets_for_user(payload, language=language)

    if intent in {"track_follow_up", "tracking_followup"} or payload.get("tracking_number"):
        return format_tracking_for_user(payload, language=language)

    text = format_payload_as_french(payload, tool_hint=tool_name or intent)
    return finalize_reply(text, language=language)


def finalize_reply(text: str, *, language: str = "fr", tool_payloads: list | None = None) -> str:
    """Dernière passe — supprime JSON, prefixes techniques, Copilot indisponible."""
    t = (text or "").strip()
    t = _RAW_TOOL_PREFIX_RE.sub("", t)
    if re.search(r"^R[eé]sultat\s+\w+", t, re.I):
        t = re.sub(r"^R[eé]sultat\s+\w+\s*:\s*", "", t, flags=re.I)
    t = sanitize_reply(t, tool_payloads=tool_payloads)
    if "copilot indisponible" in t.lower():
        if language == "fr":
            return "Je n'ai pas pu accéder à toutes les données. Réessayez ou reformulez votre question."
        return "I could not access all data. Please retry or rephrase."
    return t


def format_security_for_user(payload: dict[str, Any], *, language: str = "fr") -> str:
    count = payload.get("open_incidents_count") or payload.get("count") or payload.get("total") or payload.get("open_count") or 0
    critical = payload.get("critical_count") or payload.get("critical") or 0
    high = payload.get("high_count") or payload.get("elevated") or 0
    risk = payload.get("risk_level") or ("faible" if critical == 0 and high == 0 else "moyen" if critical == 0 else "élevé")

    if language == "fr":
        lines = [
            "## Rapport sécurité",
            "",
            f"**{count}** incident(s) de sécurité ouvert(s).",
            f"**Incidents critiques :** {critical}",
            f"**Sévérité élevée :** {high}",
            f"**Niveau de risque :** {risk}",
        ]
        if count and critical == 0 and high:
            lines.append(f"\n*{count} incidents ouverts, 0 critiques, plusieurs à sévérité élevée.*")
        elif count and critical == 0:
            lines.append("\n*Aucun incident critique détecté.*")
        lines.extend(["", "**Recommandations :**", "- Surveiller les tentatives de prompt injection", "- Vérifier les accès admin récents"])
    else:
        lines = [f"**{count}** open security incident(s). Critical: {critical}. Risk: {risk}."]
    return "\n".join(lines)


def format_tickets_for_user(payload: dict[str, Any], *, language: str = "fr") -> str:
    if payload.get("status") == "error":
        if language == "fr":
            return "Je n'ai pas pu accéder au module tickets. Vérifiez analyze_tickets ou la table tickets."
        return "Could not access tickets module."

    count = payload.get("count", len(payload.get("tickets") or []))
    if count == 0:
        return "0 ticket ouvert actuellement." if language == "fr" else "0 open tickets currently."

    lines = [f"**{count}** ticket(s) ouvert(s) :" if language == "fr" else f"**{count}** open ticket(s):"]
    for t in (payload.get("tickets") or [])[:8]:
        if isinstance(t, dict):
            lines.append(f"- #{t.get('id', '?')} — {str(t.get('subject', ''))[:80]} ({t.get('status', '?')})")
    return "\n".join(lines)


def format_tracking_for_user(payload: dict[str, Any], *, language: str = "fr") -> str:
    if payload.get("status") == "error":
        tn = payload.get("tracking_number") or "?"
        return f"Colis **{tn}** introuvable." if language == "fr" else f"Package **{tn}** not found."

    tn = payload.get("tracking_number") or "—"
    status = payload.get("status") or payload.get("fedex_status") or "—"
    location = payload.get("current_location") or "—"
    user = payload.get("user_name") or "—"
    email = payload.get("user_email") or "—"
    delayed = payload.get("is_delayed", False)

    if language == "fr":
        lines = [
            f"**Colis {tn}**",
            f"- Statut : **{status}**",
            f"- Localisation : {location}",
            f"- Utilisateur lié : {user} ({email})",
        ]
        if delayed:
            lines.append("- **Retard ou anomalie détectée.**")
        else:
            lines.append("- Aucun retard signalé pour le moment.")
    else:
        lines = [f"**Package {tn}** — Status: **{status}**", f"Location: {location}"]
    return "\n".join(lines)


def format_tracking_creator(payload: dict[str, Any], *, language: str = "fr") -> str:
    user = payload.get("user_name") or "—"
    email = payload.get("user_email") or "—"
    tn = payload.get("tracking_number") or "—"
    if language == "fr":
        return f"Le suivi du colis **{tn}** a été créé par **{user}** ({email})."
    return f"Tracking for **{tn}** was created by **{user}** ({email})."


def format_tracking_delay(payload: dict[str, Any], *, language: str = "fr") -> str:
    tn = payload.get("tracking_number") or "—"
    delayed = payload.get("is_delayed", False)
    status = payload.get("status") or payload.get("fedex_status") or "—"
    if language == "fr":
        if delayed:
            return f"Oui — le colis **{tn}** présente un **retard ou une anomalie** (statut : {status})."
        return f"Non — aucun retard signalé pour le colis **{tn}** (statut : {status})."
    return f"Package **{tn}** delayed: {delayed}. Status: {status}."


def format_user_role(user: dict[str, Any], *, language: str = "fr", ordinal: int | None = None) -> str:
    role = user.get("role") or "—"
    name = user.get("full_name") or user.get("email") or "—"
    if language == "fr":
        if ordinal is not None:
            ord_labels = {0: "premier", 1: "deuxième", 2: "troisième"}
            label = ord_labels.get(ordinal, f"{ordinal + 1}e")
            return f"Le **{label} utilisateur** est **{name}**. Son rôle est : **{role}**."
        return f"Le rôle de **{name}** est : **{role}**."
    return f"**{name}** role: **{role}**."


def format_user_email(user: dict[str, Any], *, language: str = "fr", ordinal: int | None = None) -> str:
    email = user.get("email") or "—"
    name = user.get("full_name") or email
    if language == "fr":
        return f"L'email de **{name}** est : **{email}**."
    return f"**{name}** email: **{email}**."


def format_user_profile(user: dict[str, Any], *, language: str = "fr") -> str:
    name = user.get("full_name") or "—"
    email = user.get("email") or "—"
    role = user.get("role") or "—"
    status = user.get("status") or user.get("is_active", "—")
    uid = user.get("id") or "—"
    if language == "fr":
        return (
            f"**Profil utilisateur**\n"
            f"- Nom : **{name}**\n"
            f"- Email : {email}\n"
            f"- Rôle : **{role}**\n"
            f"- Statut : {status}\n"
            f"- ID : {uid}"
        )
    return f"**{name}** ({email}) — role: {role}, status: {status}"


def format_users_list(users: list[dict[str, Any]], *, language: str = "fr", limit: int = 15) -> str:
    if not users:
        return "Aucun utilisateur trouvé." if language == "fr" else "No users found."
    lines = [f"**{len(users)}** compte(s) utilisateur(s) :" if language == "fr" else f"**{len(users)}** user account(s):"]
    for i, u in enumerate(users[:limit], 1):
        name = u.get("full_name") or u.get("email") or "—"
        email = u.get("email") or "—"
        role = u.get("role") or "—"
        status = u.get("status") or ("active" if u.get("is_active") else "—")
        uid = u.get("id") or "?"
        lines.append(f"{i}. **{name}** — {email} (ID {uid}, {role}, {status})")
    if len(users) > limit:
        lines.append(f"\n*… et {len(users) - limit} autre(s).*")
    return "\n".join(lines)


def format_tracking_duration(payload: dict[str, Any], *, language: str = "fr") -> str:
    tn = payload.get("tracking_number") or "—"
    status = payload.get("status") or payload.get("fedex_status") or "—"
    updated = (
        payload.get("updated_at")
        or payload.get("last_updated")
        or payload.get("status_since")
        or payload.get("created_at")
        or "—"
    )
    location = payload.get("current_location") or "—"
    if language == "fr":
        return (
            f"Le colis **{tn}** est en statut **{status}** "
            f"(localisation : {location}). "
            f"Dernière mise à jour : {updated}."
        )
    return f"Package **{tn}** status **{status}** since {updated}."


def format_notifications_list(
    payload: dict[str, Any],
    *,
    language: str = "fr",
    limit: int | None = None,
) -> str:
    items = payload.get("sample") or payload.get("notifications") or []
    total = payload.get("count") or len(items)
    shown = items[: limit or 10]
    if not shown:
        return "Aucune notification trouvée." if language == "fr" else "No notifications found."
    lines = [
        f"**{min(len(shown), total)}** notification(s)" + (f" sur **{total}**" if total > len(shown) else "") + " :"
        if language == "fr"
        else f"**{len(shown)}** notification(s):"
    ]
    for i, n in enumerate(shown, 1):
        if isinstance(n, dict):
            title = n.get("title") or n.get("type") or "—"
            msg = str(n.get("message") or "")[:80]
            lines.append(f"{i}. **{title}** — {msg}")
    return "\n".join(lines)


def format_tracking_list(payload: dict[str, Any], *, language: str = "fr") -> str:
    items = payload.get("sample") or payload.get("trackings") or []
    if not items:
        return "Aucun colis trouvé." if language == "fr" else "No packages found."
    lines = [f"**{len(items)}** opération(s) tracking :" if language == "fr" else f"**{len(items)}** tracking operation(s):"]
    for t in items[:10]:
        if isinstance(t, dict):
            tn = t.get("tracking_number") or "?"
            status = t.get("status") or t.get("fedex_status") or "—"
            lines.append(f"- **{tn}** — {status}")
    return "\n".join(lines)


def build_clean_api_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise la réponse API finale."""
    answer = finalize_reply(
        raw.get("answer") or raw.get("reply") or "",
        language=raw.get("language") or "fr",
    )
    export = raw.get("export_download") or {}
    return {
        "reply": answer,
        "answer": answer,
        "language": raw.get("language") or "fr",
        "mode": raw.get("mode") or raw.get("llm_provider") or "deterministic",
        "intent": raw.get("intent") or "general",
        "tools_used": raw.get("tools_used") or [],
        "download_url": raw.get("download_url") or export.get("url") or export.get("download_url"),
        "file_name": raw.get("file_name") or export.get("filename"),
        "confidence": raw.get("confidence", 0.85),
        "error": raw.get("error"),
        "copilot_state": raw.get("copilot_state") or {},
        "export_download": export or None,
        "action_executed": raw.get("action_executed", False),
    }
