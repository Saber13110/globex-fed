"""Routeur utilisateurs admin — Ollama JSON fallback (phrases ambiguës)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan

logger = logging.getLogger(__name__)

ADMIN_USERS_ROUTER_PROMPT = """Tu es le routeur Gestion utilisateurs admin Globex FedEx (Jarvis Super Admin).
Analyse le MESSAGE et choisis UNE tâche utilisateurs.

TÂCHES AUTORISÉES :
- user_list : lister / filtrer utilisateurs (rôle, statut, recherche)
- user_detail : fiche détail d'un utilisateur
- user_logs : journaux d'activité d'un utilisateur
- user_permissions : rôle, statut, quotas
- user_suspend : suspendre un compte (pas admin)
- user_reactivate : réactiver un compte
- user_delete : supprimer un compte
- user_update_name : renommer (new_name requis)
- user_reset_password : réinitialiser MDP (SMTP)
- ambiguous : hors gestion utilisateurs ou trop vague

RÈGLES :
- suivi colis / tracking → ambiguous
- notifications → ambiguous
- KPI dashboard (nouveaux users, répartition par rôle) → ambiguous
- centre de rapports → ambiguous
- answers.user_id : entier si # utilisateur cité
- answers.role_filter : client | employe | admin
- answers.status_filter : active | suspended | pending | invited
- answers.search_query : email ou nom (liste uniquement)
- Si message trop vague → needs_clarification=true avec UNE question courte

Réponds UNIQUEMENT en JSON valide :
{
  "task_type": "user_list|user_detail|user_logs|user_permissions|user_suspend|user_reactivate|user_delete|user_update_name|user_reset_password|ambiguous",
  "assistant_intro": "",
  "answers": {"user_id": null, "role_filter": "", "status_filter": "", "search_query": "", "new_name": "", "suspend_reason": ""},
  "ready_to_execute": true,
  "needs_clarification": false,
  "clarification_question": ""
}"""

_VALID_TASKS = frozenset({
    "user_list",
    "user_detail",
    "user_logs",
    "user_permissions",
    "user_suspend",
    "user_reactivate",
    "user_delete",
    "user_update_name",
    "user_reset_password",
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


def plan_admin_users_task(
    message: str,
    *,
    conversation_history: str | None = None,
    ui_language: str = "fr",
) -> dict[str, Any] | None:
    user_block = f"MESSAGE:\n{message.strip()}"
    if conversation_history:
        user_block += f"\n\nHISTORIQUE:\n{conversation_history[-4000:]}"

    try:
        raw = call_ollama_agent_plan(
            system_prompt=ADMIN_USERS_ROUTER_PROMPT,
            user_message=user_block,
            ui_language=ui_language,
        )
    except LlmProviderError as exc:
        logger.warning("users_router ollama failed: %s", exc)
        return None

    data = _parse_json_object(raw or "")
    if not data:
        return None
    return _plan_from_data(data)
