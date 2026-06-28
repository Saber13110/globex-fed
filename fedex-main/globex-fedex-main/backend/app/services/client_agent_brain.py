# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
"""Cerveau agent client : planification et conversation (Gemini ou Ollama)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.llm.prompts import AGENT_BRAIN_PROMPT, language_lock_instruction

logger = logging.getLogger(__name__)

TASK_CONVERSATION = "conversation"
TASK_TRACK = "track_package"

_VALID_TASKS = frozenset(
    {
        "watch_shipment",
        "stop_watch",
        "export_excel",
        "support_ticket",
        "summary_report",
        "multi_track",
        "pod_delivery",
        "track_package",
        "task_picker",
        TASK_CONVERSATION,
    }
)


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


def _gemini_agent_call(prompt: str, *, ui_language: str = "fr", max_tokens: int = 512) -> str | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        from app.services.llm.providers import _gemini_generate, gemini_api_key_usable

        if not gemini_api_key_usable():
            return None
        return _gemini_generate(prompt, max_output_tokens=max_tokens, ui_language=ui_language)
    except Exception:
        logger.warning("Appel Gemini agent brain échoué", exc_info=True)
        return None
# #
# #
# # def _plan_from_data(data: dict[str, Any], *, ui_language: str) -> dict[str, Any]:
# #     task = str(data.get("task_type") or data.get("action_tool") or "task_picker").strip()
# #     if task not in _VALID_TASKS:
# #         task = "task_picker"
# #
# #     answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
# #     answers = {str(k): str(v) for k, v in answers.items() if v is not None and str(v).strip()}
# #
# #     plan_raw = data.get("plan")
# #     plan_steps: list[str] = []
# #     if isinstance(plan_raw, list):
# #         plan_steps = [str(p).strip() for p in plan_raw if str(p).strip()][:5]
# #     elif isinstance(plan_raw, str) and plan_raw.strip():
# #         plan_steps = [s.strip() for s in plan_raw.split("\n") if s.strip()][:5]
# #
# #     action_tool = str(data.get("action_tool") or task).strip()
# #
# #     return {
# #         "objective": str(data.get("objective") or "").strip(),
# #         "plan": plan_steps,
# #         "action_tool": action_tool,
# #         "verification": str(data.get("verification") or "").strip(),
# #         "task_type": task,
# #         "answers": answers,
# #         "assistant_intro": str(data.get("assistant_intro") or data.get("understood") or "").strip(),
# #         "ready_to_execute": bool(data.get("ready_to_execute", False)),
# #         "needs_clarification": bool(data.get("needs_clarification", False)),
# #         "clarification_question": str(data.get("clarification_question") or "").strip(),
# #         "llm_provider": "gemini",
# #     }
# #
# #
# # def _plan_agent_action_rules(message: str) -> dict[str, Any] | None:
# #     """Repli local quand Gemini est indisponible."""
# #     from app.services.client_agent_service import TASK_PICKER, TASK_TRACK, detect_agent_task, is_simple_tracking_request
# #
# #     if is_simple_tracking_request(message):
# #         return {
# #             "objective": "Suivre le colis et répondre au client",
# #             "plan": ["Consulter FedEx", "Répondre avec le statut"],
# #             "action_tool": TASK_TRACK,
# #             "verification": "Le client reçoit le statut du colis",
# #             "task_type": TASK_TRACK,
# #             "answers": {},
# #             "assistant_intro": "",
# #             "ready_to_execute": True,
# #             "needs_clarification": False,
# #             "clarification_question": "",
# #             "llm_provider": "rules",
# #         }
# #
# #     task = detect_agent_task(message)
# #     if task and task != TASK_PICKER:
# #         return {
# #             "objective": "",
# #             "plan": [],
# #             "action_tool": task,
# #             "verification": "",
# #             "task_type": task,
# #             "answers": {},
# #             "assistant_intro": "",
# #             "ready_to_execute": False,
# #             "needs_clarification": False,
# #             "clarification_question": "",
# #             "llm_provider": "rules",
# #         }
# #     return None
# #
# #
# # def plan_agent_action(
# #     message: str,
# #     *,
# #     conversation_history: str | None = None,
# #     session_tracking_numbers: list[str] | None = None,
# #     user_name: str | None = None,
# #     ui_language: str = "fr",
# # ) -> dict[str, Any] | None:
# #     """
# #     Analyse la demande et retourne un plan structuré (Gemini, sinon règles locales).
# #     """
# #     tn_list = session_tracking_numbers or []
# #     ctx = ""
# #     if conversation_history:
# #         ctx += f"\n\nHISTORIQUE RÉCENT:\n{conversation_history[:2500]}"
# #     if tn_list:
# #         ctx += f"\n\nCOLIS DE LA SESSION: {', '.join(tn_list)}"
# #
# #     lang_rule = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
# #     prompt = (
# #         f"{AGENT_BRAIN_PROMPT}\n\n{lang_rule}\n"
# #         f"CLIENT: {user_name or 'Client'}\n"
# #         f"{ctx}\n\n"
# #         f"MESSAGE UTILISATEUR:\n{message.strip()[:1200]}\n\n"
# #         "Réponds UNIQUEMENT avec le JSON (pas de markdown autour si possible)."
# #     )
# #     raw = _gemini_agent_call(prompt, ui_language=ui_language, max_tokens=640)
# #     if raw:
# #         data = _parse_json_object(raw)
# #         if data:
# #             return _plan_from_data(data, ui_language=ui_language)
# #         logger.debug("Plan agent non-JSON: %s", raw[:200])
#
#     return _plan_agent_action_rules(message)
#
#
def verify_agent_result(
    *,
    objective: str,
    verification: str,
    task: str,
    technical_result: str,
    steps_summary: str = "",
    ui_language: str = "fr",
) -> dict[str, Any]:
    """
    Vérifie si le résultat d'exécution répond à l'objectif (sans inventer de données).
    Retourne {verified: bool|None, note: str}.
    """
    if not objective.strip() or not technical_result.strip():
        return {"verified": None, "note": ""}

    lang_rule = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
    prompt = (
        f"{lang_rule}\n\n"
        "Tu es le contrôleur qualité de l'agent FedEx.\n"
        "Compare l'OBJECTIF et le CRITÈRE DE VÉRIFICATION avec le RÉSULTAT RÉEL d'exécution.\n"
        "RÈGLES : ne jamais inventer de données ; si le résultat indique une erreur ou une info manquante, verified=false.\n"
        "Réponds UNIQUEMENT en JSON : {\"verified\": true|false, \"note\": \"phrase courte\"}\n\n"
        f"OBJECTIF : {objective[:500]}\n"
        f"CRITÈRE VÉRIFICATION : {verification[:400] or 'Le client obtient ce quil a demandé'}\n"
        f"TÂCHE EXÉCUTÉE : {task}\n"
        f"RÉSULTAT RÉEL :\n{technical_result[:2000]}\n"
    )
    if steps_summary:
        prompt += f"\nÉTAPES :\n{steps_summary[:600]}\n"

    raw = _gemini_agent_call(prompt, ui_language=ui_language, max_tokens=200)
    if not raw:
        return {"verified": None, "note": ""}

    data = _parse_json_object(raw)
    if not data:
        return {"verified": None, "note": ""}

    verified = data.get("verified")
    if verified is not None:
        verified = bool(verified)
    return {
        "verified": verified,
        "note": str(data.get("note") or "").strip(),
    }
# #
# #
# # def build_reasoning_payload(
# #     brain_plan: dict[str, Any] | None,
# #     *,
# #     task_label: str,
# #     verified: bool | None = None,
# #     verification_note: str = "",
# # ) -> dict[str, Any]:
# #     """Construit le bloc agent_reasoning pour la réponse API."""
# #     if not brain_plan:
# #         return {}
# #     return {
# #         "objective": brain_plan.get("objective") or "",
# #         "plan": brain_plan.get("plan") or [],
# #         "action_tool": brain_plan.get("action_tool") or brain_plan.get("task_type") or "",
# #         "action_label": task_label,
# #         "verification": brain_plan.get("verification") or "",
# #         "verified": verified,
# #         "verification_note": verification_note,
# #     }
# #
# #
# # def synthesize_agent_reply(
# #     *,
# #     user_message: str,
# #     task: str,
# #     task_label: str,
# #     technical_reply: str,
# #     steps_summary: str = "",
# #     ui_language: str = "fr",
# # ) -> str | None:
# #     """Reformule le résultat d'exécution en réponse naturelle (voix de l'agent)."""
# #     if not technical_reply.strip():
# #         return None
# #     lang_rule = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
# #     from app.services.gpt.writing_style import professional_writing_for_lang
# #
# #     prompt = (
# #         f"{lang_rule}\n\n{professional_writing_for_lang(ui_language)}\n\n"
# #         "Vous êtes l'agent FedEx Globex. Reformulez le RÉSULTAT RÉEL pour le client.\n"
# #         "Confirmez ce qui a été fait, en prose professionnelle et sobre (3–6 phrases).\n"
# #         "Ne jamais inventer de statut, date, lieu ou action absente du résultat.\n"
# #         "Pas de jargon technique. **Gras** possible pour numéros de colis.\n\n"
# #         f"Demande client : {user_message[:400]}\n"
# #         f"Tâche : {task_label} ({task})\n"
# #         f"Résultat :\n{technical_reply[:2000]}\n"
# #     )
# #     if steps_summary:
# #         prompt += f"\nÉtapes exécutées:\n{steps_summary[:800]}\n"
# #     prompt += "\nRéponse naturelle:"
# #     synthesized = _gemini_agent_call(prompt, ui_language=ui_language, max_tokens=400)
# #     if synthesized:
# #         return synthesized
# #     return technical_reply.strip() or None
# #
# #
# # def converse_in_agent_mode(
# #     message: str,
# #     *,
# #     conversation_history: str | None = None,
# #     fedex_context_json: str | None = None,
# #     ui_language: str = "fr",
# #     preferred_name: str | None = None,
# #     intent: str = "track_package",
# #     tracking_number: str | None = None,
# # ) -> tuple[str | None, str | None]:
# #     """Réponse conversationnelle FedEx (Ollama ou Gemini selon config)."""
# #     from app.services.gpt.model_gateway import generate_with_context
# #     from app.services.gpt.orchestrator import SLUG_CLIENT
# #
# #     parts: list[str] = []
# #     if preferred_name:
# #         parts.append(f"Prénom client : {preferred_name.strip()}")
# #     if conversation_history:
# #         parts.append(f"CONVERSATION_HISTORY:\n{conversation_history[-2000:]}")
# #     if fedex_context_json:
# #         parts.append(f"FEDEX_DATA:\n{fedex_context_json[:6000]}")
# #     if tracking_number:
# #         parts.append(f"Numéro de suivi actif : {tracking_number}")
# #     parts.append(f"QUESTION_CLIENT:\n{message.strip()}")
# #     payload = "\n\n".join(parts)
# #
# #     try:
# #         result = generate_with_context(
# #             gpt_slug=SLUG_CLIENT,
# #             user_payload=payload,
# #             ui_language=ui_language,
# #             max_output_tokens=600,
# #         )
# #         return result.reply, result.llm_provider
# #     except Exception:
# #         logger.warning("Conversation agent LLM échouée", exc_info=True)
# #         return None, None
