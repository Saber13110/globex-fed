"""
Handlers rapides ciblés — cas spécifiques sans modifier l'architecture existante.

- get_top_platform_issues() : top 5 problèmes, cache 60s, < 3s
- get_suspicious_activity_summary() : résumé logs/sécurité
- fetch_suspended_users() / export suspended XLSX
"""

from __future__ import annotations

import io
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.export_dataset_cache import store_export_dataset
from app.services.ai_assistant.export_pipeline import build_export_response_spec
from app.services.ai_assistant.export_normalize import normalize_items_for_export
from app.services.ai_assistant.intent_classifier_v2 import ClassifiedIntent, CopilotIntent
from app.services.ai_assistant.safe_tool_executor import execute_tool_plan
from app.services.ai_assistant.user_suspension_logic import (
    filter_suspended_users,
    get_suspended_users,
    get_suspendable_users,
)
from app.services.ai_assistant.conversation_state import ConversationState

logger = logging.getLogger(__name__)

_ISSUES_CACHE: dict[str, tuple[float, str, list[str]]] = {}
_ISSUES_CACHE_TTL = 60.0
_FAST_DEADLINE = 3.0

_TOP_ISSUES_PLAN = [
    ("get_security_alerts", {"limit": 12}),
    ("get_open_tickets", {"status": "open", "limit": 10}),
    ("get_platform_stats", {}),
]


def _parse_top_limit(message: str, default: int = 5) -> int:
    m = re.search(r"\b(\d+)\s+probl[eè]mes?\b", message, re.I)
    if m:
        return min(max(int(m.group(1)), 1), 10)
    return default


def get_top_platform_issues(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str = "fr",
) -> tuple[str, list[str], bool]:
    """
    Classement rapide des problèmes plateforme.
    Retourne (answer, tools_used, from_cache).
    """
    cache_key = f"top_issues:{admin.id}"
    now = time.monotonic()
    cached = _ISSUES_CACHE.get(cache_key)
    if cached and cached[0] > now:
        logger.info("[Targeted] top_platform_issues cache hit")
        return cached[1], cached[2], True

    deadline = time.monotonic() + _FAST_DEADLINE
    results = execute_tool_plan(
        db, admin, _TOP_ISSUES_PLAN, deadline=deadline, ui_language=lang,
    )
    tools_used = [r["name"] for r in results if r.get("ok")]

    issues: list[tuple[int, str, str]] = []  # (priority, category, description)

    for r in results:
        name = r["name"]
        payload = r.get("response") or {}
        if payload.get("status") == "error":
            continue

        if "security" in name:
            incidents = payload.get("incidents") or payload.get("sample") or []
            for inc in incidents[:8]:
                if not isinstance(inc, dict):
                    continue
                sev = str(inc.get("severity") or inc.get("level") or "medium").lower()
                pri = 1 if sev in {"critical", "critique", "high", "élevé", "eleve"} else 2
                title = inc.get("title") or inc.get("type") or inc.get("message") or "Incident sécurité"
                issues.append((pri, "Sécurité", str(title)[:120]))

            open_count = payload.get("open_count") or payload.get("count") or len(incidents)
            critical = payload.get("critical_count") or payload.get("critical") or 0
            if open_count and not incidents:
                issues.append((2, "Sécurité", f"{open_count} incident(s) ouvert(s), dont {critical} critique(s)"))

        elif "ticket" in name:
            for tk in (payload.get("tickets") or [])[:8]:
                if not isinstance(tk, dict):
                    continue
                subj = tk.get("subject") or tk.get("title") or f"Ticket #{tk.get('id', '?')}"
                pri = 2 if str(tk.get("priority", "")).lower() in {"high", "critical", "urgent"} else 3
                issues.append((pri, "Tickets", str(subj)[:120]))

        elif "platform" in name or "stats" in name:
            delayed = payload.get("delayed_shipments") or payload.get("delayed") or 0
            if delayed:
                issues.append((2, "Tracking", f"{delayed} expédition(s) en retard"))
            errors = payload.get("errors_today") or payload.get("error_count") or 0
            if errors:
                issues.append((2, "Système", f"{errors} erreur(s) système aujourd'hui"))

    issues.sort(key=lambda x: x[0])
    limit = _parse_top_limit(message)

    if lang == "fr":
        if not issues:
            answer = (
                "## Problèmes prioritaires plateforme\n\n"
                "Aucun problème critique détecté actuellement.\n\n"
                f"*Analyse rapide — {len(tools_used)} source(s) consultée(s).*"
            )
        else:
            lines = ["## Problèmes prioritaires plateforme", ""]
            for i, (_, cat, desc) in enumerate(issues[:limit], 1):
                lines.append(f"{i}. **[{cat}]** {desc}")
            lines.append("")
            lines.append(f"*Analyse rapide — {len(tools_used)} source(s) — cache 60 s.*")
            answer = "\n".join(lines)
    else:
        if not issues:
            answer = "No critical platform issues detected."
        else:
            lines = ["## Top platform issues", ""]
            for i, (_, cat, desc) in enumerate(issues[:limit], 1):
                lines.append(f"{i}. **[{cat}]** {desc}")
            answer = "\n".join(lines)

    _ISSUES_CACHE[cache_key] = (now + _ISSUES_CACHE_TTL, answer, tools_used)
    return answer, tools_used, False


def fetch_users_by_status(
    db: Session,
    admin: User,
    *,
    status: str,
    lang: str = "fr",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Récupère les utilisateurs filtrés par statut via analyze_users."""
    if status in {"suspended", "suspendu", "suspendus"}:
        return get_suspended_users(db, admin, lang=lang)

    deadline = time.monotonic() + _FAST_DEADLINE
    results = execute_tool_plan(
        db, admin,
        [("get_users_summary", {"limit": 100, "status": status})],
        deadline=deadline,
        ui_language=lang,
    )
    payload = results[0]["response"] if results else {}
    users = payload.get("users") if isinstance(payload.get("users"), list) else []
    tools = [r["name"] for r in results if r.get("ok")]
    return users, payload, tools


def format_suspendable_users_list(
    users: list[dict[str, Any]],
    *,
    lang: str = "fr",
    as_section: bool = False,
) -> str:
    if not users:
        if lang == "fr":
            return "Aucun compte à surveiller / suspension recommandée."
        return "No accounts flagged for monitoring / recommended suspension."

    if lang == "fr":
        header = (
            f"**{len(users)}** compte(s) à surveiller / suspension recommandée :"
            if not as_section
            else (
                f"**{len(users)}** compte(s) est/sont toutefois à surveiller "
                f"car une alerte recommande une suspension potentielle :"
            )
        )
    else:
        header = f"**{len(users)}** account(s) to monitor / recommended for suspension:"

    lines = [header, ""]
    for u in users[:20]:
        name = u.get("full_name") or u.get("email") or "—"
        email = u.get("email") or "—"
        role = u.get("role") or "—"
        risk = u.get("risk_score") or "—"
        reasons = u.get("reasons") or []
        reason = reasons[0] if reasons else "—"
        action = u.get("recommended_action") or "monitor"
        lines.append(
            f"- **{name}** — {email} — rôle : **{role}** — "
            f"risque : **{risk}** — motif : {reason} — action : **{action}**"
        )
    return "\n".join(lines)


def format_suspended_users_list(
    users: list[dict[str, Any]],
    total: int,
    *,
    suspendable: list[dict[str, Any]] | None = None,
    lang: str = "fr",
) -> str:
    if not users:
        if lang == "fr":
            lines = ["Aucun compte utilisateur n'est actuellement suspendu."]
        else:
            lines = ["No user account is currently suspended."]
        if suspendable:
            lines.append("")
            lines.append(format_suspendable_users_list(suspendable, lang=lang, as_section=True))
        return "\n".join(lines)

    lines = [
        f"**Comptes suspendus : {len(users)}**",
        "",
    ]
    for u in users[:20]:
        name = u.get("full_name") or u.get("email") or "—"
        email = u.get("email") or "—"
        role = u.get("role") or "—"
        suspended_at = u.get("suspended_at") or u.get("updated_at") or u.get("created_at") or "—"
        reason = u.get("suspension_reason") or u.get("reason") or ""
        line = f"- **{name}** — {email} — rôle : **{role}** — suspendu le : {suspended_at}"
        if reason:
            line += f" — raison : {reason}"
        lines.append(line)
    return "\n".join(lines)


def format_no_suspended_export_message(*, lang: str = "fr") -> str:
    if lang == "fr":
        return (
            "Aucun compte réellement suspendu n'a été trouvé. "
            "Je peux générer un fichier Excel des comptes à surveiller/suspendables si vous le souhaitez."
        )
    return (
        "No truly suspended account was found. "
        "I can generate an Excel file of accounts to monitor if you wish."
    )


def _generate_users_xlsx_bytes(
    users: list[dict[str, Any]],
    *,
    sheet_title: str = "Utilisateurs suspendus",
    headers: list[str] | None = None,
) -> bytes:
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    hdrs = headers or ["Nom", "Email", "Rôle", "Statut", "ID"]
    ws.append(hdrs)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for u in users:
        if headers and "Risque" in headers:
            ws.append([
                u.get("full_name") or u.get("nom") or "",
                u.get("email") or "",
                u.get("role") or "",
                u.get("risk_score") or "",
                "; ".join(u.get("reasons") or [])[:200],
                u.get("recommended_action") or "",
                u.get("id") or "",
            ])
        else:
            ws.append([
                u.get("full_name") or u.get("nom") or "",
                u.get("email") or "",
                u.get("role") or "",
                u.get("status") or u.get("statut") or "suspended",
                u.get("id") or "",
            ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_suspended_users_xlsx(
    db: Session,
    admin: User,
    users: list[dict[str, Any]],
    *,
    lang: str = "fr",
) -> dict[str, Any]:
    """Export XLSX des comptes réellement suspendus uniquement."""
    verified = filter_suspended_users(users)
    normalized = normalize_items_for_export(verified, "users")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"users-suspended-{len(normalized)}-items-{ts}.xlsx"
    xlsx_bytes = _generate_users_xlsx_bytes(normalized)

    export_token = store_export_dataset(
        admin_id=admin.id,
        module="users",
        items=normalized,
        limit=len(normalized),
        source="suspended_verified",
        filename=filename,
        fmt="xlsx",
        meta={"xlsx_bytes_len": len(xlsx_bytes), "filter": "suspended_verified"},
    )

    export_spec = build_export_response_spec(
        module="users",
        filename=filename,
        records=len(normalized),
        export_token=export_token,
        fmt="xlsx",
        limit=len(normalized),
    )
    export_spec["download_url"] = (
        f"/admin/ai-assistant/export/context.xlsx"
        f"?export_token={export_token}&preset=admin_users&limit={len(normalized)}"
    )

    if lang == "fr":
        reply = (
            f"Excel généré avec succès : **{len(normalized)}** compte(s) réellement suspendu(s) exporté(s).\n"
            f"Téléchargez : **{filename}**"
        )
    else:
        reply = (
            f"Excel generated: **{len(normalized)}** truly suspended account(s) exported.\n"
            f"Download: **{filename}**"
        )

    return {
        "reply": reply,
        "answer": reply,
        "tools_used": ["analyze_users"],
        "intent": "export_suspended_users",
        "mode": "deterministic",
        "confidence": 0.92,
        "action_executed": True,
        "export_download": export_spec,
        "file_name": filename,
        "download_url": export_spec.get("download_url"),
    }


def export_suspendable_users_xlsx(
    db: Session,
    admin: User,
    users: list[dict[str, Any]],
    *,
    lang: str = "fr",
) -> dict[str, Any]:
    """Export XLSX des comptes à surveiller / suspension recommandée."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"users-suspendable-{len(users)}-items-{ts}.xlsx"
    export_rows = [
        {
            "nom": u.get("full_name") or u.get("email") or "",
            "email": u.get("email") or "",
            "role": u.get("role") or "",
            "statut": "à_surveiller",
            "id": u.get("id") or "",
            "risk_score": u.get("risk_score") or "",
            "reasons": u.get("reasons") or [],
            "recommended_action": u.get("recommended_action") or "",
        }
        for u in users
    ]
    xlsx_bytes = _generate_users_xlsx_bytes(
        export_rows,
        sheet_title="Comptes à surveiller",
        headers=["Nom", "Email", "Rôle", "Risque", "Motif", "Action recommandée", "ID"],
    )

    export_token = store_export_dataset(
        admin_id=admin.id,
        module="users",
        items=export_rows,
        limit=len(export_rows),
        source="suspendable_filter",
        filename=filename,
        fmt="xlsx",
        meta={"xlsx_bytes_len": len(xlsx_bytes), "filter": "suspendable"},
    )

    export_spec = build_export_response_spec(
        module="users",
        filename=filename,
        records=len(export_rows),
        export_token=export_token,
        fmt="xlsx",
        limit=len(export_rows),
    )
    export_spec["download_url"] = (
        f"/admin/ai-assistant/export/context.xlsx"
        f"?export_token={export_token}&preset=admin_users&limit={len(export_rows)}"
    )

    if lang == "fr":
        reply = (
            f"Excel généré : **{len(export_rows)}** compte(s) à surveiller / suspension recommandée.\n"
            f"Téléchargez : **{filename}**"
        )
    else:
        reply = (
            f"Excel generated: **{len(export_rows)}** account(s) to monitor.\n"
            f"Download: **{filename}**"
        )

    return {
        "reply": reply,
        "answer": reply,
        "tools_used": ["analyze_users", "get_security_alerts"],
        "intent": "export_suspendable_users",
        "mode": "deterministic",
        "confidence": 0.91,
        "action_executed": True,
        "export_download": export_spec,
        "file_name": filename,
        "download_url": export_spec.get("download_url"),
    }


def get_suspicious_activity_summary(
    db: Session,
    admin: User,
    *,
    lang: str = "fr",
) -> tuple[str, list[str]]:
    """Résumé rapide activités suspectes — sans timeout Gemini."""
    deadline = time.monotonic() + _FAST_DEADLINE
    results = execute_tool_plan(
        db, admin,
        [
            ("analyze_suspicious_logs", {"hours": 24}),
            ("get_security_alerts", {"limit": 15}),
        ],
        deadline=deadline,
        ui_language=lang,
    )
    tools_used = [r["name"] for r in results if r.get("ok")]

    suspicious_count = 0
    severity = "faible"
    events: list[str] = []
    blocked = 0
    injections = 0

    for r in results:
        payload = r.get("response") or {}
        if "suspicious" in r["name"]:
            evts = payload.get("suspicious_events") or payload.get("events") or []
            suspicious_count = len(evts) if isinstance(evts, list) else payload.get("count", 0)
            score = payload.get("risk_score") or payload.get("score") or 0
            if score >= 7 or suspicious_count >= 5:
                severity = "élevé"
            elif score >= 3 or suspicious_count >= 1:
                severity = "moyen"
            for ev in (evts if isinstance(evts, list) else [])[:5]:
                if isinstance(ev, dict):
                    events.append(ev.get("description") or ev.get("action") or str(ev)[:80])
                else:
                    events.append(str(ev)[:80])
        if "security" in r["name"]:
            incidents = payload.get("incidents") or payload.get("sample") or []
            for inc in incidents:
                if not isinstance(inc, dict):
                    continue
                t = str(inc.get("type") or inc.get("title") or "").lower()
                if "injection" in t or "prompt" in t:
                    injections += 1
                if "block" in t or "bloqu" in t:
                    blocked += 1

    if lang == "fr":
        lines = [
            "## Activités suspectes — résumé",
            "",
            f"**Événements suspects détectés :** {suspicious_count}",
            f"**Niveau de gravité :** {severity}",
        ]
        if injections:
            lines.append(f"**Tentatives d'injection détectées :** {injections}")
        if blocked:
            lines.append(f"**Comptes/actions bloqués :** {blocked}")
        if events:
            lines.append("")
            lines.append("**Principaux événements :**")
            for i, ev in enumerate(events[:5], 1):
                lines.append(f"{i}. {ev}")
        elif suspicious_count == 0:
            lines.append("")
            lines.append("Aucune activité suspecte significative détectée dans les dernières 24 h.")
        answer = "\n".join(lines)
    else:
        answer = f"**Suspicious events:** {suspicious_count}. **Severity:** {severity}."

    return answer, tools_used


def format_security_alerts_summary(payload: dict[str, Any], *, lang: str = "fr") -> str:
    count = payload.get("open_count") or payload.get("count") or len(payload.get("incidents") or [])
    critical = payload.get("critical_count") or payload.get("critical") or 0
    high = payload.get("high_count") or payload.get("high") or 0
    incidents = payload.get("incidents") or payload.get("sample") or []

    if lang == "fr":
        lines = [f"**{count}** alerte(s) sécurité ouverte(s).", f"**Critiques :** {critical} | **Élevées :** {high}", ""]
        for inc in incidents[:8]:
            if isinstance(inc, dict):
                lines.append(f"- {inc.get('title') or inc.get('type') or 'Incident'} ({inc.get('severity', '?')})")
        return "\n".join(lines)
    return f"**{count}** open security alert(s). Critical: {critical}."


def format_open_incidents(payload: dict[str, Any], *, lang: str = "fr") -> str:
    count = payload.get("open_count") or payload.get("count") or len(payload.get("incidents") or [])
    incidents = payload.get("incidents") or payload.get("sample") or []
    if count == 0:
        return "0 incident ouvert actuellement." if lang == "fr" else "0 open incidents."
    lines = [f"**{count}** incident(s) ouvert(s) :" if lang == "fr" else f"**{count}** open incident(s):"]
    for inc in incidents[:10]:
        if isinstance(inc, dict):
            lines.append(f"- {inc.get('title') or inc.get('type') or 'Incident'} — {inc.get('severity', '?')}")
    return "\n".join(lines)


def format_critical_tickets(payload: dict[str, Any], *, lang: str = "fr") -> str:
    tickets = payload.get("tickets") or []
    critical = [t for t in tickets if isinstance(t, dict) and str(t.get("priority", "")).lower() in {"high", "critical", "urgent"}]
    if not critical:
        if lang == "fr":
            return f"Aucun ticket critique ouvert ({len(tickets)} ticket(s) ouvert(s) au total)."
        return f"No critical open tickets ({len(tickets)} open total)."
    lines = [f"**{len(critical)}** ticket(s) critique(s) ouvert(s) :" if lang == "fr" else f"**{len(critical)}** critical ticket(s):"]
    for t in critical[:8]:
        lines.append(f"- #{t.get('id', '?')} — {str(t.get('subject', ''))[:80]}")
    return "\n".join(lines)


def try_targeted_handler(
    db: Session,
    admin: User,
    message: str,
    *,
    intent: ClassifiedIntent,
    conv: ConversationState,
    lang: str = "fr",
) -> dict[str, Any] | None:
    """Dispatch handlers ciblés — retourne réponse API ou None."""
    name = intent.name

    if name == CopilotIntent.TOP_PLATFORM_ISSUES:
        answer, tools, from_cache = get_top_platform_issues(db, admin, message, lang=lang)
        conv.record_tool_success("get_platform_stats", {}, intent=name.value)
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.93 if not from_cache else 0.95,
            "reasoning_summary": "Analyse rapide multi-sources (cache 60 s)." if from_cache else "Analyse rapide multi-sources.",
        }

    if name == CopilotIntent.SUSPICIOUS_ACTIVITY:
        answer, tools = get_suspicious_activity_summary(db, admin, lang=lang)
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.88,
        }

    if name == CopilotIntent.LIST_SUSPENDED_USERS:
        users, payload, tools = get_suspended_users(db, admin, lang=lang)
        suspendable: list[dict[str, Any]] = []
        if not users:
            suspendable, _, _ = get_suspendable_users(db, admin, lang=lang)
        total = payload.get("total") or 0
        answer = format_suspended_users_list(
            users, total, suspendable=suspendable if not users else None, lang=lang,
        )
        conv.record_tool_success("analyze_users", payload, intent=name.value)
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.91,
        }

    if name == CopilotIntent.LIST_SUSPENDABLE_USERS:
        users, _meta, tools = get_suspendable_users(db, admin, lang=lang)
        answer = format_suspendable_users_list(users, lang=lang)
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.9,
        }

    if name == CopilotIntent.COUNT_ACTIVE_USERS:
        deadline = time.monotonic() + _FAST_DEADLINE
        results = execute_tool_plan(
            db, admin, [("get_users_summary", {"limit": 50})],
            deadline=deadline, ui_language=lang,
        )
        payload = results[0]["response"] if results and results[0].get("ok") else {}
        tools = [r["name"] for r in results if r.get("ok")]
        count = payload.get("active")
        if count is None:
            users_mem = conv.get_users_list()
            if users_mem:
                count = sum(
                    1 for u in users_mem
                    if str(u.get("status", "")).lower() in {"active", "actif"}
                )
        if count is None:
            users = payload.get("users") or []
            count = sum(
                1 for u in users
                if str(u.get("status", "")).lower() in {"active", "actif"}
            )
        count = count or 0
        if lang == "fr":
            answer = f"**{count}** utilisateur(s) sont actuellement actifs."
        else:
            answer = f"**{count}** user(s) are currently active."
        conv.record_tool_success("analyze_users", payload, intent=name.value)
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools or ["analyze_users"], "confidence": 0.92,
        }

    if name == CopilotIntent.EXPORT_SUSPENDED_USERS:
        users, payload, tools = get_suspended_users(db, admin, lang=lang)
        if not users:
            msg = format_no_suspended_export_message(lang=lang)
            return {
                "reply": msg, "answer": msg, "language": lang,
                "mode": "deterministic", "intent": name.value,
                "tools_used": tools, "confidence": 0.9, "action_executed": False,
            }
        result = export_suspended_users_xlsx(db, admin, users, lang=lang)
        conv.record_tool_success("analyze_users", payload, intent=name.value)
        result["language"] = lang
        return result

    if name == CopilotIntent.EXPORT_SUSPENDABLE_USERS:
        users, _meta, tools = get_suspendable_users(db, admin, lang=lang)
        if not users:
            msg = (
                "Aucun compte à surveiller / suspension recommandée détecté."
                if lang == "fr"
                else "No accounts flagged for monitoring."
            )
            return {
                "reply": msg, "answer": msg, "language": lang,
                "mode": "deterministic", "intent": name.value,
                "tools_used": tools, "confidence": 0.88, "action_executed": False,
            }
        result = export_suspendable_users_xlsx(db, admin, users, lang=lang)
        result["language"] = lang
        return result

    if name == CopilotIntent.SECURITY_ALERTS:
        results = execute_tool_plan(
            db, admin, [("get_security_alerts", {"limit": 20})],
            deadline=time.monotonic() + _FAST_DEADLINE, ui_language=lang,
        )
        payload = results[0]["response"] if results else {}
        answer = format_security_alerts_summary(payload, lang=lang)
        tools = [r["name"] for r in results if r.get("ok")]
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.9,
        }

    if name == CopilotIntent.OPEN_INCIDENTS:
        results = execute_tool_plan(
            db, admin, [("get_security_alerts", {"limit": 20})],
            deadline=time.monotonic() + _FAST_DEADLINE, ui_language=lang,
        )
        payload = results[0]["response"] if results else {}
        answer = format_open_incidents(payload, lang=lang)
        tools = [r["name"] for r in results if r.get("ok")]
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.9,
        }

    if name == CopilotIntent.CRITICAL_TICKETS:
        results = execute_tool_plan(
            db, admin, [("get_open_tickets", {"status": "open", "limit": 30})],
            deadline=time.monotonic() + _FAST_DEADLINE, ui_language=lang,
        )
        payload = results[0]["response"] if results else {}
        answer = format_critical_tickets(payload, lang=lang)
        tools = [r["name"] for r in results if r.get("ok")]
        return {
            "reply": answer, "answer": answer, "language": lang,
            "mode": "deterministic", "intent": name.value,
            "tools_used": tools, "confidence": 0.9,
        }

    return None
