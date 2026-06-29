"""Routeur reports admin — Ollama JSON fallback (phrases ambiguës)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan

logger = logging.getLogger(__name__)

ADMIN_REPORTS_ROUTER_PROMPT = """Tu es le routeur Centre de rapports admin Globex FedEx (Jarvis Super Admin).
Analyse le MESSAGE et choisis UNE tâche reports.

TÂCHES AUTORISÉES :
- report_list_recent : lister exports récents, catalogue, historique
- report_preview : prévisualiser / aperçu du contenu d'un export
- report_redownload : re-télécharger un export (Excel, CSV, JSON, PDF)
- report_share : partager un rapport par e-mail (avec destinataire si connu)
- ambiguous : hors centre de rapports ou trop vague

RÈGLES :
- suivi colis / numéro tracking → ambiguous
- notifications cloche → ambiguous
- PDF d'un colis précis → ambiguous
- « rapport des retards » plateforme → ambiguous (dashboard)
- e-mail à un utilisateur / client / ticket traité / compte suspendu → ambiguous (agent e-mail user, PAS report_share)
- report_share UNIQUEMENT si partage d'un export/rapport admin (ReportRun) avec mot rapport/report/export explicite
- answers.run_id : entier si # rapport cité
- answers.format_filter : xlsx | csv | json | pdf si format explicite
- answers.slug_hint : tracking-history | financial-summary | delivery-performance | exception-report si nom cité
- answers.recipient_query : email ou nom si partage
- Si message trop vague (« reports » seul) → needs_clarification=true avec UNE question courte

Réponds UNIQUEMENT en JSON valide :
{
  "task_type": "report_list_recent|report_preview|report_redownload|report_share|ambiguous",
  "assistant_intro": "",
  "answers": {"run_id": null, "format_filter": "", "slug_hint": "", "recipient_query": ""},
  "ready_to_execute": true,
  "needs_clarification": false,
  "clarification_question": ""
}"""

_VALID_TASKS = frozenset({
    "report_list_recent",
    "report_preview",
    "report_redownload",
    "report_share",
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


def plan_admin_reports_task(
    message: str,
    *,
    conversation_history: str | None = None,
    ui_language: str = "fr",
) -> dict[str, Any] | None:
    """Planifie une tâche reports via Ollama JSON. None si ambiguous ou échec."""
    try:
        raw = call_ollama_agent_plan(
            message,
            system_prompt=ADMIN_REPORTS_ROUTER_PROMPT,
            conversation_history=conversation_history,
            ui_language=ui_language,
        )
    except LlmProviderError:
        logger.warning("[admin_reports] routeur Ollama indisponible", exc_info=True)
        return None

    data = _parse_json_object(raw)
    if not data:
        logger.info("[admin_reports] routeur JSON invalide: %.120s", raw or "")
        return None

    plan = _plan_from_data(data)
    if plan["task_type"] == "ambiguous" and not plan.get("needs_clarification"):
        return None
    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return plan
    if plan["task_type"] in _ACTION_TASKS and plan.get("ready_to_execute"):
        return plan
    return None
