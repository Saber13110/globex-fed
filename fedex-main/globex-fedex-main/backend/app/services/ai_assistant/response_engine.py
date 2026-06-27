"""Moteur de réponses adaptées — COUNT, LIST, ANALYZE, EXPORT, etc."""

from __future__ import annotations

from typing import Any

from app.services.ai_assistant.intent_router_v2 import ActionType, IntentV2


def format_tool_response(
    intent: IntentV2,
    tool_name: str,
    payload: dict[str, Any],
    *,
    ui_language: str = "fr",
    message: str = "",
) -> str:
    """Convertit un payload outil en réponse adaptée à l'intention."""
    action = intent.action
    if action == "COUNT":
        return _format_count(intent, payload, ui_language)
    if action == "EXPORT":
        return _format_export(intent, payload, ui_language)
    if action == "SUMMARIZE":
        return _format_summarize(intent, payload, tool_name, ui_language, message=message)
    if action == "ANALYZE":
        return _format_analyze(intent, payload, tool_name, ui_language, message=message)
    if action == "TRACK":
        return _format_tracking(payload, ui_language)
    return _format_list(intent, tool_name, payload, ui_language, message=message)


def _format_count(intent: IntentV2, payload: dict[str, Any], lang: str) -> str:
    domain = intent.domain
    filters = intent.filters or {}

    if domain == "users":
        if filters.get("status") == "active":
            n = payload.get("active", 0)
            return f"**{n}** utilisateur{'s' if n != 1 else ''} actif{'s' if n != 1 else ''}." if lang == "fr" else f"**{n}** active user(s)."
        if filters.get("status") == "suspended":
            n = payload.get("suspended", 0)
            return f"**{n}** utilisateur{'s' if n != 1 else ''} suspendu{'s' if n != 1 else ''}." if lang == "fr" else f"**{n}** suspended user(s)."
        n = payload.get("total", payload.get("count", 0))
        return f"**{n}** utilisateur{'s' if n != 1 else ''} au total." if lang == "fr" else f"**{n}** total user(s)."

    if domain == "notifications":
        n = payload.get("total", payload.get("count", len(payload.get("sample") or [])))
        unread = payload.get("unread_count", 0)
        if lang == "fr":
            return f"**{n}** notification{'s' if n != 1 else ''} ({unread} non lue{'s' if unread != 1 else ''})."
        return f"**{n}** notification(s) ({unread} unread)."

    if domain == "tickets":
        n = payload.get("count", len(payload.get("tickets") or []))
        return f"**{n}** ticket{'s' if n != 1 else ''}." if lang == "fr" else f"**{n}** ticket(s)."

    if domain == "logs":
        n = payload.get("count", len(payload.get("sample") or []))
        return f"**{n}** entrée{'s' if n != 1 else ''} de journal." if lang == "fr" else f"**{n}** log entries."

    n = payload.get("count", payload.get("total", 0))
    return f"**{n}** élément{'s' if n != 1 else ''}." if lang == "fr" else f"**{n}** item(s)."


def _format_list(
    intent: IntentV2,
    tool_name: str,
    payload: dict[str, Any],
    lang: str,
    message: str = "",
) -> str:
    """Liste formatée — délègue au formateur dégradé existant pour cohérence."""
    from app.services.gpt.tool_synthesis import degraded_format_tool_payload

    return degraded_format_tool_payload(
        tool_name, payload, message=message, ui_language=lang,
    )


def _format_analyze(
    intent: IntentV2,
    payload: dict[str, Any],
    tool_name: str,
    lang: str,
    message: str = "",
) -> str:
    from app.services.gpt.tool_synthesis import degraded_format_tool_payload

    base = degraded_format_tool_payload(tool_name, payload, message=message, ui_language=lang)
    if lang == "fr":
        rec = "\n\n**Recommandations :** Surveillez les alertes critiques et traitez les éléments non lus en priorité."
    else:
        rec = "\n\n**Recommendations:** Monitor critical alerts and prioritize unread items."
    return base + rec


def _format_summarize(
    intent: IntentV2,
    payload: dict[str, Any],
    tool_name: str,
    lang: str,
    message: str = "",
) -> str:
    from app.services.gpt.tool_synthesis import degraded_format_tool_payload

    base = degraded_format_tool_payload(tool_name, payload, message=message, ui_language=lang)
    if lang == "fr":
        return f"**Résumé :**\n{base[:800]}"
    return f"**Summary:**\n{base[:800]}"


def _format_export(intent: IntentV2, payload: dict[str, Any], lang: str) -> str:
    spec = payload.get("export_download") or {}
    filename = spec.get("filename") or payload.get("filename") or "export.pdf"
    count = payload.get("count", len(payload.get("preview") or payload.get("sample") or []))
    fmt = intent.export_format or spec.get("format") or "pdf"
    if lang == "fr":
        return (
            f"Export **{fmt.upper()}** prêt — **{count}** élément(s).\n"
            f"Téléchargez : **{filename}**."
        )
    return f"**{fmt.upper()}** export ready — **{count}** item(s).\nDownload: **{filename}**."


def _format_tracking(payload: dict[str, Any], lang: str) -> str:
    tn = payload.get("tracking_number") or payload.get("trackingNumber") or "—"
    status = payload.get("status") or payload.get("status_description") or payload.get("message") or "—"
    if lang == "fr":
        return f"**Colis {tn}** — Statut : **{status}**"
    return f"**Package {tn}** — Status: **{status}**"


def should_skip_llm_synthesis(intent: IntentV2) -> bool:
    """COUNT et EXPORT contextuel n'ont pas besoin de resynthèse LLM."""
    return intent.action in {"COUNT", "EXPORT"}
