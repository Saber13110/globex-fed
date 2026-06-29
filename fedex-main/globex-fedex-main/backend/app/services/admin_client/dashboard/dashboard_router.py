"""Routeur dashboard admin — Ollama JSON fallback (phrases ambiguës)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan

logger = logging.getLogger(__name__)

ADMIN_DASHBOARD_ROUTER_PROMPT = """Tu es le routeur dashboard admin Globex FedEx (Jarvis Super Admin).
Analyse le MESSAGE et choisis UNE tâche dashboard.

TÂCHES AUTORISÉES :
- platform_overview : KPI, état plateforme, santé système, situation globale
- delayed_shipments : colis en retard, problématiques, at risk
- quick_delay_report : rapport retards (texte ou PDF/graphiques)
- recent_activity : activité récente, timeline
- recent_ai_conversations : conversations IA récentes
- recent_audit : audit, logs admin, activité suspecte
- users_breakdown : répartition utilisateurs par rôle/statut
- new_users_period : nouveaux utilisateurs (période)
- ambiguous : hors dashboard ou trop vague

RÈGLES :
- suivi colis / numéro tracking → ambiguous
- notifications cloche → ambiguous
- PDF d'un colis précis → ambiguous
- « rapport des retards » / « delay report » → quick_delay_report
- answers.period : today | week | month (défaut today)
- answers.limit : entier 1-50 (défaut 10)
- answers.suspicious_only : true si activité suspecte / intrusion
- answers.include_pdf : true si PDF/export explicite pour rapport retards

Réponds UNIQUEMENT en JSON valide :
{
  "task_type": "platform_overview|delayed_shipments|quick_delay_report|recent_activity|recent_ai_conversations|recent_audit|users_breakdown|new_users_period|ambiguous",
  "assistant_intro": "",
  "answers": {"period": "today", "limit": 10, "suspicious_only": false, "include_charts": false, "include_pdf": false},
  "ready_to_execute": true,
  "needs_clarification": false,
  "clarification_question": ""
}"""

_VALID_TASKS = frozenset({
    "platform_overview",
    "delayed_shipments",
    "quick_delay_report",
    "recent_activity",
    "recent_ai_conversations",
    "recent_audit",
    "users_breakdown",
    "new_users_period",
    "ambiguous",
})

_ACTION_TASKS = _VALID_TASKS - {"ambiguous"}


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
    task = str(data.get("task_type") or "ambiguous").strip()
    if task not in _VALID_TASKS:
        task = "ambiguous"

    answers_raw = data.get("answers")
    answers: dict[str, Any] = {}
    if isinstance(answers_raw, dict):
        answers = {str(k): v for k, v in answers_raw.items() if v is not None}

    return {
        "task_type": task,
        "assistant_intro": str(data.get("assistant_intro") or "").strip(),
        "answers": answers,
        "ready_to_execute": bool(data.get("ready_to_execute", task in _ACTION_TASKS)),
        "needs_clarification": bool(data.get("needs_clarification", False)),
        "clarification_question": str(data.get("clarification_question") or "").strip(),
    }


def plan_admin_dashboard_task(
    message: str,
    *,
    conversation_history: str | None = None,
    ui_language: str = "fr",
) -> dict[str, Any] | None:
    """Planifie une tâche dashboard via Ollama JSON. None si ambiguous ou échec."""
    try:
        raw = call_ollama_agent_plan(
            message,
            system_prompt=ADMIN_DASHBOARD_ROUTER_PROMPT,
            conversation_history=conversation_history,
            ui_language=ui_language,
        )
    except LlmProviderError:
        logger.warning("[admin_dashboard] routeur Ollama indisponible", exc_info=True)
        return None

    data = _parse_json_object(raw)
    if not data:
        logger.info("[admin_dashboard] routeur JSON invalide: %.120s", raw or "")
        return None

    plan = _plan_from_data(data)
    if plan["task_type"] == "ambiguous":
        return None
    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return plan
    if plan["task_type"] in _ACTION_TASKS and plan.get("ready_to_execute"):
        return plan
    return None
