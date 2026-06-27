"""Analytics et rapports déterministes rapides — sans attente Gemini."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


def format_top_active_users(
    users_payload: dict[str, Any],
    logs_payload: dict[str, Any] | None,
    *,
    lang: str = "fr",
    limit: int = 10,
) -> str:
    """Classement activité utilisateurs depuis logs + users."""
    users = users_payload.get("users") or users_payload.get("sample") or []
    logs = (logs_payload or {}).get("sample") or []

    activity: Counter[str] = Counter()
    name_by_id: dict[str, str] = {}
    email_by_id: dict[str, str] = {}

    for u in users:
        if not isinstance(u, dict):
            continue
        uid = str(u.get("id") or u.get("user_id") or "")
        if uid:
            name_by_id[uid] = u.get("full_name") or u.get("name") or u.get("email") or f"User {uid}"
            email_by_id[uid] = u.get("email") or ""

    for log in logs:
        if not isinstance(log, dict):
            continue
        uid = str(log.get("user_id") or log.get("actor_id") or "")
        email = (log.get("user_email") or log.get("email") or "").lower()
        if uid:
            activity[uid] += 1
        elif email:
            activity[email] += 1

    if not activity and not logs:
        if lang == "fr":
            return (
                "Je peux lister les utilisateurs, mais l'activité détaillée nécessite "
                "les logs utilisateur ou une table activity_logs."
            )
        return (
            "I can list users, but detailed activity requires user logs or an activity_logs table."
        )

    if not activity:
        if lang == "fr":
            return (
                "Je peux lister les utilisateurs, mais l'activité détaillée nécessite "
                "les logs utilisateur ou une table activity_logs."
            )
        return "Detailed activity ranking requires user activity logs."

    ranked = activity.most_common(limit)
    lines = ["**Voici les utilisateurs les plus actifs :**" if lang == "fr" else "**Most active users:**", ""]
    for i, (key, count) in enumerate(ranked, start=1):
        label = name_by_id.get(key) or email_by_id.get(key) or key
        suffix = " action(s)" if lang == "fr" else " action(s)"
        lines.append(f"{i}. **{label}** — {count}{suffix}")
    return "\n".join(lines)


def format_notification_frequency(
    payload: dict[str, Any],
    *,
    lang: str = "fr",
    limit: int = 8,
) -> str:
    """Regroupe les notifications par type/titre."""
    items = payload.get("sample") or payload.get("notifications") or []
    if not items:
        if lang == "fr":
            return "Aucune notification disponible pour l'analyse de fréquence."
        return "No notifications available for frequency analysis."

    counter: Counter[str] = Counter()
    for n in items:
        if not isinstance(n, dict):
            continue
        label = (
            n.get("type")
            or n.get("notification_type")
            or n.get("title")
            or n.get("subject")
            or "Autre"
        )
        counter[str(label).strip() or "Autre"] += 1

    ranked = counter.most_common(limit)
    header = "**Types les plus fréquents :**" if lang == "fr" else "**Most frequent types:**"
    lines = [header, ""]
    for i, (label, count) in enumerate(ranked, start=1):
        lines.append(f"{i}. **{label}** — {count}")
    return "\n".join(lines)


def format_security_report_fast(payload: dict[str, Any], *, lang: str = "fr") -> str:
    """Synthèse sécurité déterministe."""
    sec = payload.get("security") or payload
    count = sec.get("open_incidents_count") or sec.get("count") or sec.get("total") or 0
    critical = sec.get("critical_count") or 0
    risk = sec.get("risk_level") or ("élevé" if critical >= 3 else "moyen" if critical else "faible")
    recs = sec.get("recommendations") or [
        "Surveiller les tentatives de prompt injection",
        "Vérifier les accès admin récents",
        "Traiter les incidents ouverts",
    ]
    if lang == "fr":
        lines = [
            "## Rapport sécurité",
            "",
            f"**Incidents ouverts :** {count}",
            f"**Niveau de risque :** {risk}",
            f"**Critiques :** {critical}",
            "",
            "**Recommandations :**",
        ]
    else:
        lines = [
            "## Security report",
            "",
            f"**Open incidents:** {count}",
            f"**Risk level:** {risk}",
            f"**Critical:** {critical}",
            "",
            "**Recommendations:**",
        ]
    for r in recs[:5]:
        lines.append(f"- {r}")
    return "\n".join(lines)


def format_suspicious_activity_fast(payload: dict[str, Any], *, lang: str = "fr") -> str:
    """Synthèse activités suspectes."""
    suspicious = payload.get("suspicious_events") or payload.get("suspicious") or []
    login_fail = payload.get("login_failures") or 0
    injection = payload.get("injection_hits") or 0
    risk = "élevé" if injection >= 2 or login_fail >= 5 else "moyen" if login_fail or injection else "faible"
    if lang == "fr":
        lines = [
            "## Activités suspectes",
            "",
            f"**Niveau de risque :** {risk}",
            f"**Échecs de connexion :** {login_fail}",
            f"**Tentatives injection :** {injection}",
            f"**Événements suspects :** {len(suspicious)}",
        ]
    else:
        lines = [
            "## Suspicious activity",
            "",
            f"**Risk level:** {risk}",
            f"**Login failures:** {login_fail}",
            f"**Injection attempts:** {injection}",
            f"**Suspicious events:** {len(suspicious)}",
        ]
    for ev in suspicious[:5]:
        if isinstance(ev, dict):
            lines.append(f"- {ev.get('type', '?')} : {ev.get('detail', '')[:100]}")
    return "\n".join(lines)


def format_platform_health_fast(payloads: list[dict[str, Any]], *, lang: str = "fr") -> str:
    """Rapport santé plateforme déterministe multi-outils."""
    data: dict[str, dict] = {}
    for p in payloads:
        data[p.get("name", "")] = p.get("response") or {}

    stats = data.get("get_platform_stats") or data.get("kpis") or {}
    users = data.get("get_users_summary") or data.get("analyze_users") or {}
    tracking = data.get("get_tracking_summary") or data.get("analyze_tracking") or {}
    notifs = data.get("get_notifications_summary") or data.get("analyze_notifications") or {}
    security = data.get("get_security_alerts") or data.get("analyze_security") or {}
    tickets = data.get("get_open_tickets") or data.get("analyze_tickets") or {}

    if lang == "fr":
        lines = [
            "## Rapport de santé — Globex FedEx",
            "",
            "### Statut général",
            "Analyse basée sur les données vérifiées des outils backend.",
            "",
            "### Utilisateurs",
            f"- Actifs : **{users.get('active', users.get('total', '—'))}**",
            "",
            "### Expéditions",
            f"- Total récent : **{tracking.get('total', '—')}**",
            f"- Retards : **{tracking.get('delayed_count', 0)}**",
            "",
            "### Notifications",
            f"- Volume : **{notifs.get('total', notifs.get('count', '—'))}**",
            "",
            "### Sécurité",
            f"- Incidents : **{security.get('count', security.get('total', 0))}**",
            "",
            "### Tickets",
            f"- Ouverts : **{tickets.get('count', len(tickets.get('tickets') or []))}**",
            "",
            "### Recommandations",
            "- Surveiller les retards colis et incidents sécurité ouverts.",
            "- Traiter les tickets prioritaires.",
        ]
    else:
        lines = [
            "## Platform health — Globex FedEx",
            "",
            f"### Users\n- Active: **{users.get('active', '—')}**",
            f"### Tracking\n- Total: **{tracking.get('total', '—')}**",
            f"### Security\n- Incidents: **{security.get('count', 0)}**",
        ]
    if stats:
        lines.insert(4, f"- KPI plateforme : **{stats.get('active_users', stats.get('shipments_today', 'OK'))}**")
    return "\n".join(lines)
