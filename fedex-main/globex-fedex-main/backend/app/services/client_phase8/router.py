"""
Routeur Phase 8 — rapport d'activité quotidien client.

Branchement depuis chatbot_service avant try_client_sessions_turn.
Requiert CLIENT_AGENT_ROUTER_ENABLED=true et cap daily_report.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_session_context import build_conversation_history_for_llm
from app.services.client_phase8.capabilities import has_daily_report_capability, router_enabled
from app.services.client_phase8.daily_report_executor import execute_send_daily_report
from app.services.client_phase8.daily_report_intent import (
    fallback_plan_from_message,
    is_daily_report_workspace,
    is_schedule_time_clarification_followup,
    parse_schedule_time_followup,
    schedule_time_clarification_message,
)
from app.services.client_phase8.router_prompt import (
    CLIENT_DAILY_REPORT_ROUTER_PROMPT,
    CLIENT_DAILY_REPORT_ROUTER_RETRY_PROMPT,
)
from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan

logger = logging.getLogger(__name__)

_VALID_TASKS = frozenset({"send_daily_report", "configure_schedule", "disable_schedule", "conversation"})
_REPORT_TASKS = frozenset({"send_daily_report", "configure_schedule", "disable_schedule"})


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
    return {
        "task_type": task,
        "assistant_intro": str(data.get("assistant_intro") or "").strip(),
        "answers": answers,
        "ready_to_execute": bool(data.get("ready_to_execute", False)),
        "needs_clarification": bool(data.get("needs_clarification", False)),
        "clarification_question": str(data.get("clarification_question") or "").strip(),
    }


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def _schedule_unavailable_message(lang: str) -> str:
    if lang == "en":
        return (
            "Automatic daily reports are not available at the moment. "
            'Say "send my daily report by email" to receive it now.'
        )
    return (
        "L'envoi automatique n'est pas disponible pour l'instant. "
        "Dites « envoyez mon rapport du jour par mail » pour le recevoir maintenant."
    )


def _last_bot_message_text(db: Session, session_id: int) -> str | None:
    row = db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.sender == MessageSender.bot.value,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    raw = getattr(row, "message_text", None)
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def _call_ollama_plan(
    message: str,
    *,
    history: str,
    ui_language: str | None,
    system_prompt: str = CLIENT_DAILY_REPORT_ROUTER_PROMPT,
) -> dict[str, Any] | None:
    raw = call_ollama_agent_plan(
        message,
        system_prompt=system_prompt,
        conversation_history=history,
        session_titles="",
        ui_language=ui_language,
    )
    data = _parse_json_object(raw)
    if data:
        return _plan_from_data(data)
    logger.info("Phase 8 router non-JSON: %s", (raw or "")[:200])
    return None


def _turn_result(reply: str, intent: str) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "agent_daily_report",
        "intent": intent,
        "tracking_number": None,
        "llm_provider": "ollama",
        "shipment": None,
        "export_download": None,
    }


def _reconcile_plan(message: str, plan: dict[str, Any], *, lang: str) -> dict[str, Any]:
    task = plan.get("task_type")
    answers = dict(plan.get("answers") or {})
    if task == "configure_schedule":
        rt = str(answers.get("run_time") or "").strip()
        if not rt:
            from app.services.client_phase8.daily_report_preferences import parse_run_time

            rt = parse_run_time(message) or ""
        if rt:
            answers["run_time"] = rt
            plan["answers"] = answers
            plan["ready_to_execute"] = True
            plan["needs_clarification"] = False
        elif plan.get("needs_clarification"):
            plan["clarification_question"] = plan.get("clarification_question") or schedule_time_clarification_message(lang)
        else:
            plan["needs_clarification"] = True
            plan["ready_to_execute"] = False
            plan["clarification_question"] = schedule_time_clarification_message(lang)
    return plan


def _clarification_followup_plan(
    db: Session,
    session_id: int,
    message: str,
    *,
    lang: str,
) -> dict[str, Any] | None:
    last_bot = _last_bot_message_text(db, session_id)
    if not last_bot or not is_schedule_time_clarification_followup(last_bot):
        return None
    rt = parse_schedule_time_followup(message)
    if not rt:
        return {
            "task_type": "configure_schedule",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": schedule_time_clarification_message(lang),
        }
    return {
        "task_type": "configure_schedule",
        "assistant_intro": "",
        "answers": {"run_time": rt},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }


def plan_daily_report_task(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    lang = _lang(ui_language, user)
    history = build_conversation_history_for_llm(
        db,
        session_id=session.id,
        exclude_message_id=exclude_message_id,
        limit=4,
    )

    if is_daily_report_workspace(message):
        fb = fallback_plan_from_message(message, lang=lang)
        if fb and fb.get("ready_to_execute") and not fb.get("needs_clarification"):
            return _reconcile_plan(message, fb, lang=lang)

    plan: dict[str, Any] | None = None
    ollama_failed = False

    try:
        plan = _call_ollama_plan(message, history=history, ui_language=ui_language)
    except LlmProviderError:
        ollama_failed = True
        logger.warning("Phase 8 router Ollama unavailable", exc_info=True)

    if plan and plan.get("task_type") in _REPORT_TASKS:
        return _reconcile_plan(message, plan, lang=lang)

    if not ollama_failed and is_daily_report_workspace(message):
        try:
            retry = _call_ollama_plan(
                message,
                history=history,
                ui_language=ui_language,
                system_prompt=CLIENT_DAILY_REPORT_ROUTER_RETRY_PROMPT,
            )
            if retry and retry.get("task_type") in _REPORT_TASKS:
                return _reconcile_plan(message, retry, lang=lang)
        except LlmProviderError:
            logger.warning("Phase 8 router Ollama retry unavailable", exc_info=True)

    if is_daily_report_workspace(message):
        fallback = fallback_plan_from_message(message, lang=lang)
        if fallback:
            return _reconcile_plan(message, fallback, lang=lang)
    return None


def _execute_plan(
    db: Session,
    user: User,
    plan: dict[str, Any],
    *,
    ui_language: str | None,
) -> dict[str, Any]:
    task = plan.get("task_type")
    lang = _lang(ui_language, user)

    if task == "conversation":
        return _turn_result("", "conversation")

    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return _turn_result(plan["clarification_question"], task or "daily_report_clarify")

    intro = plan.get("assistant_intro") or ""
    answers = dict(plan.get("answers") or {})

    if task == "disable_schedule":
        return _turn_result(_schedule_unavailable_message(lang), "schedule_unavailable")

    if task == "configure_schedule":
        return _turn_result(_schedule_unavailable_message(lang), "schedule_unavailable")

    if task == "send_daily_report":
        try:
            ok, msg, _ = execute_send_daily_report(db, user, lang=lang)
        except Exception:
            logger.exception("Phase 8 send_daily_report failed")
            if lang == "en":
                err = "Unable to generate your daily report. Please try again in a moment."
            else:
                err = "Impossible de générer votre rapport d'activité. Réessayez dans un instant."
            return _turn_result(err, "send_daily_report_failed")
        reply = f"{intro}\n\n{msg}".strip() if intro else msg
        intent = "send_daily_report" if ok else "send_daily_report_failed"
        return _turn_result(reply, intent)

    return _turn_result("", "conversation")


def try_client_daily_report_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    if not router_enabled() or not has_daily_report_capability():
        return None

    lang = _lang(ui_language, user)

    followup = _clarification_followup_plan(db, session.id, message, lang=lang)
    if followup is not None:
        return _turn_result(_schedule_unavailable_message(lang), "schedule_unavailable")

    if not is_daily_report_workspace(message):
        return None

    plan = plan_daily_report_task(
        db,
        user,
        session,
        message,
        exclude_message_id=exclude_message_id,
        ui_language=ui_language,
    )
    if plan is None or plan.get("task_type") == "conversation":
        return None

    return _execute_plan(db, user, plan, ui_language=ui_language)
