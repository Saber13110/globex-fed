"""
Routeur Phase 6 — surveillance colis + alertes mail.

Branchement depuis chatbot_service après try_client_notifications_turn.
Requiert CLIENT_AGENT_ROUTER_ENABLED=true et cap watch.
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
from app.services.client_phase6.capabilities import has_watch_capability, router_enabled
from app.services.client_phase6.router_prompt import (
    CLIENT_WATCH_ROUTER_PROMPT,
    CLIENT_WATCH_ROUTER_RETRY_PROMPT,
)
from app.services.client_phase6.watch_executor import execute_activate_watch, execute_stop_watch
from app.services.client_phase6.watch_intent import (
    email_limit_clarification_message,
    fallback_plan_from_message,
    is_alert_ambiguous_clarification_followup,
    is_email_limit_clarification_followup,
    is_tracking_clarification_followup,
    is_unlimited_email_message,
    is_watch_workspace,
    parse_alert_ambiguous_reply,
    parse_email_limit_reply,
    reconcile_watch_plan,
    tracking_clarification_message,
)
from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

_VALID_TASKS = frozenset({"activate_watch", "stop_watch", "conversation"})
_WATCH_TASKS = frozenset({"activate_watch", "stop_watch"})


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


def _call_ollama_watch_plan(
    message: str,
    *,
    history: str,
    ui_language: str | None,
    system_prompt: str = CLIENT_WATCH_ROUTER_PROMPT,
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
    logger.info("Phase 6 router non-JSON: %s", (raw or "")[:200])
    return None


def _turn_result(reply: str, intent: str) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "agent_watch",
        "intent": intent,
        "tracking_number": None,
        "llm_provider": "ollama",
        "shipment": None,
        "export_download": None,
    }


def _clarification_followup_plan(
    db: Session,
    session_id: int,
    message: str,
    *,
    lang: str,
) -> dict[str, Any] | None:
    last_bot = _last_bot_message_text(db, session_id)
    if not last_bot:
        return None

    if is_alert_ambiguous_clarification_followup(last_bot):
        choice = parse_alert_ambiguous_reply(message)
        if choice == "view":
            return None
        if choice == "activate":
            return {
                "task_type": "activate_watch",
                "assistant_intro": "",
                "answers": {"notify_email": True, "notify_in_app": True},
                "ready_to_execute": False,
                "needs_clarification": True,
                "clarification_question": tracking_clarification_message(lang),
            }
        return None

    pending_answers: dict[str, Any] = {}

    if is_email_limit_clarification_followup(last_bot):
        limit = parse_email_limit_reply(message)
        if limit == "invalid":
            return {
                "task_type": "activate_watch",
                "assistant_intro": "",
                "answers": {},
                "ready_to_execute": False,
                "needs_clarification": True,
                "clarification_question": email_limit_clarification_message(lang),
            }
        pending_answers["max_email_updates"] = limit
        tn = extract_tracking_number(message)
        if tn:
            pending_answers["tracking_number"] = tn
            return {
                "task_type": "activate_watch",
                "assistant_intro": "",
                "answers": pending_answers,
                "ready_to_execute": True,
                "needs_clarification": False,
                "clarification_question": "",
            }
        return {
            "task_type": "activate_watch",
            "assistant_intro": "",
            "answers": pending_answers,
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": tracking_clarification_message(lang),
        }

    if is_tracking_clarification_followup(last_bot):
        tn = extract_tracking_number(message)
        if not tn:
            return {
                "task_type": "activate_watch",
                "assistant_intro": "",
                "answers": {},
                "ready_to_execute": False,
                "needs_clarification": True,
                "clarification_question": tracking_clarification_message(lang),
            }
        pending_answers["tracking_number"] = tn
        limit = parse_email_limit_reply(message)
        if limit != "invalid" and (limit is not None or is_unlimited_email_message(message)):
            pending_answers["max_email_updates"] = limit
            pending_answers.setdefault("notify_email", True)
            pending_answers.setdefault("notify_in_app", True)
            return {
                "task_type": "activate_watch",
                "assistant_intro": "",
                "answers": pending_answers,
                "ready_to_execute": True,
                "needs_clarification": False,
                "clarification_question": "",
            }
        return {
            "task_type": "activate_watch",
            "assistant_intro": "",
            "answers": pending_answers,
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": email_limit_clarification_message(lang),
        }

    return None


def plan_watch_task(
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
    plan: dict[str, Any] | None = None
    ollama_failed = False

    try:
        plan = _call_ollama_watch_plan(message, history=history, ui_language=ui_language)
    except LlmProviderError:
        ollama_failed = True
        logger.warning("Phase 6 router Ollama unavailable", exc_info=True)

    if plan and plan.get("task_type") in _WATCH_TASKS:
        finalized = reconcile_watch_plan(message, plan, lang=lang)
        logger.info("Phase 6 plan task=%s source=ollama", finalized.get("task_type"))
        return finalized

    if not ollama_failed and is_watch_workspace(message):
        try:
            retry_plan = _call_ollama_watch_plan(
                message,
                history=history,
                ui_language=ui_language,
                system_prompt=CLIENT_WATCH_ROUTER_RETRY_PROMPT,
            )
            if retry_plan and retry_plan.get("task_type") in _WATCH_TASKS:
                finalized = reconcile_watch_plan(message, retry_plan, lang=lang)
                logger.info("Phase 6 plan task=%s source=retry", finalized.get("task_type"))
                return finalized
        except LlmProviderError:
            ollama_failed = True
            logger.warning("Phase 6 router Ollama retry unavailable", exc_info=True)

    if is_watch_workspace(message):
        fallback = fallback_plan_from_message(message, lang=lang)
        if fallback:
            logger.info("Phase 6 plan task=%s source=fallback", fallback.get("task_type"))
            return fallback

    return None


def _execute_plan(
    db: Session,
    user: User,
    session: ChatSession,
    plan: dict[str, Any],
    message: str,
    *,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any]:
    task = plan.get("task_type")
    if task == "conversation":
        return _turn_result("", "conversation")

    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return _turn_result(plan["clarification_question"], task or "watch_clarify")

    intro = plan.get("assistant_intro") or ""
    answers = dict(plan.get("answers") or {})

    if task == "stop_watch":
        reply = execute_stop_watch(
            db,
            user,
            answers=answers,
            ui_language=ui_language,
            assistant_intro=intro,
        )
        return _turn_result(reply, "stop_watch")

    if task == "activate_watch":
        reply = execute_activate_watch(
            db,
            user,
            session_id=session.id,
            message=message,
            answers=answers,
            exclude_message_id=exclude_message_id,
            ui_language=ui_language,
            assistant_intro=intro,
        )
        tn = str(answers.get("tracking_number") or "").strip() or extract_tracking_number(message)
        result = _turn_result(reply, "activate_watch")
        if tn:
            result["tracking_number"] = tn
        return result

    return _turn_result("", "conversation")


def try_client_watch_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """
    Tente le routeur surveillance colis. Retourne un dict compatible _apply_early_export_turn
    ou None pour laisser le flux Phase 2/3 inchangé.
    """
    if not router_enabled() or not has_watch_capability():
        return None

    lang = _lang(ui_language, user)

    followup = _clarification_followup_plan(db, session.id, message, lang=lang)
    if followup is not None:
        if followup.get("task_type") == "conversation":
            return None
        executed = _execute_plan(
            db,
            user,
            session,
            followup,
            message,
            exclude_message_id=exclude_message_id,
            ui_language=ui_language,
        )
        if executed.get("intent") == "conversation" and not executed.get("reply"):
            return None
        return executed

    if not is_watch_workspace(message):
        return None

    plan = plan_watch_task(
        db,
        user,
        session,
        message,
        exclude_message_id=exclude_message_id,
        ui_language=ui_language,
    )
    if plan is None or plan.get("task_type") == "conversation":
        return None

    return _execute_plan(
        db,
        user,
        session,
        plan,
        message,
        exclude_message_id=exclude_message_id,
        ui_language=ui_language,
    )
