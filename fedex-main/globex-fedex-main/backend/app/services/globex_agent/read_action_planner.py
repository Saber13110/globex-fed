"""Planification lecture admin — réutilise le routeur copilot sans exports."""

from __future__ import annotations

from typing import Any

from app.services.ai_assistant.tool_planner import plan_tools
from app.services.ai_assistant.tool_registry import resolve_handler
from app.services.globex_agent.local_replies import is_capabilities_request
from app.services.gpt.intent_classifier import INTENT_CAPABILITIES, classify_intent
from app.services.gpt.orchestrator import SLUG_ADMIN


def is_capabilities_help_message(message: str) -> bool:
    return is_capabilities_request(message)


def is_capabilities_intent(message: str) -> bool:
    classification = classify_intent(message, SLUG_ADMIN)
    return classification.intent == INTENT_CAPABILITIES


def _normalize_planned_tools(
    planned: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for name, args in planned:
        canonical = resolve_handler(name)
        if canonical.startswith("export_"):
            continue
        out.append((canonical, dict(args or {})))
    return out


def plan_read_action_tools(
    message: str,
    intent: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> list[tuple[str, dict[str, Any]]] | None:
    """Route tickets/users/logs/KPI via plan_tools copilot — sans exports."""
    if intent == INTENT_CAPABILITIES:
        return None

    raw = plan_tools(
        message,
        intent,
        conversation_history=conversation_history,
    )
    if not raw:
        return None

    normalized = _normalize_planned_tools(raw)
    return normalized or None
