"""Gestion conversation — historique, résumé, langue."""

from __future__ import annotations

from typing import Any

from app.services.ai_assistant.language_service import resolve_response_language


def format_history(messages: list[dict[str, str]] | None, limit: int = 12) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for m in messages[-limit:]:
        role = m.get("role") or "user"
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content[:500]}")
    return "\n".join(lines)


def resolve_language_for_turn(
    message: str,
    *,
    profile_language: str | None,
    copilot_state: dict[str, Any] | None,
    memory_language: str | None = None,
) -> tuple[str, bool]:
    session_lang = (copilot_state or {}).get("preferred_language")
    return resolve_response_language(
        message,
        profile_language=profile_language,
        session_language=session_lang,
        memory_language=memory_language,
    )


def build_reasoning_summary(
    *,
    message: str,
    intent: str,
    planned_tools: list[str],
    tools_used: list[str],
    mode: str,
) -> str:
    parts = [f"Intention : {intent}"]
    if planned_tools:
        parts.append(f"Plan : {', '.join(planned_tools[:6])}")
    if tools_used:
        parts.append(f"Exécuté : {', '.join(tools_used)}")
    parts.append(f"Moteur : {mode}")
    return " → ".join(parts)[:500]
