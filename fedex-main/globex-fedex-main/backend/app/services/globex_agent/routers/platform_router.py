"""Routeur plateforme admin — Ollama JSON (pattern client_phase4)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.globex_agent.routers.prompts import ADMIN_PLATFORM_ROUTER_PROMPT
from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan

logger = logging.getLogger(__name__)

_VALID_TASKS = frozenset({
    "analyze_tickets",
    "analyze_users",
    "get_platform_stats",
    "analyze_security",
    "analyze_logs",
    "export_logs",
    "conversation",
})

_ACTION_TASKS = _VALID_TASKS - {"conversation"}


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _plan_from_data(data: dict[str, Any]) -> dict[str, Any]:
    task = str(data.get("task_type") or "conversation").strip()
    if task not in _VALID_TASKS:
        task = "conversation"

    answers_raw = data.get("answers")
    answers: dict[str, Any] = {}
    if isinstance(answers_raw, dict):
        answers = {str(k): v for k, v in answers_raw.items() if v is not None}

    ready = bool(data.get("ready_to_execute", False))
    if task in _ACTION_TASKS:
        ready = True

    return {
        "task_type": task,
        "assistant_intro": str(data.get("assistant_intro") or "").strip(),
        "answers": answers,
        "ready_to_execute": ready,
        "needs_clarification": bool(data.get("needs_clarification", False)),
        "clarification_question": str(data.get("clarification_question") or "").strip(),
    }


def plan_admin_platform_task(
    message: str,
    *,
    conversation_history: str | None = None,
    ui_language: str = "fr",
) -> dict[str, Any] | None:
    """Planifie une tâche admin via Ollama JSON. None si conversation ou échec."""
    try:
        raw = call_ollama_agent_plan(
            message,
            system_prompt=ADMIN_PLATFORM_ROUTER_PROMPT,
            conversation_history=conversation_history,
            ui_language=ui_language,
        )
    except LlmProviderError:
        logger.warning("[GlobexAgent] routeur plateforme Ollama indisponible", exc_info=True)
        return None

    data = _parse_json_object(raw)
    if not data:
        logger.info("[GlobexAgent] routeur plateforme JSON invalide: %.120s", raw or "")
        return None

    plan = _plan_from_data(data)
    if plan["task_type"] == "conversation":
        return None
    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return plan
    if plan["task_type"] in _ACTION_TASKS and plan.get("ready_to_execute"):
        return plan
    return None
