"""Routeur Phase 11 — ticket support intelligent."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_session_context import build_conversation_history_for_llm
from app.services.client_phase11.capabilities import has_support_ticket_capability, router_enabled
from app.services.client_phase11.router_prompt import (
    CLIENT_SUPPORT_ROUTER_PROMPT,
    CLIENT_SUPPORT_ROUTER_RETRY_PROMPT,
)
from app.services.client_phase11.ticket_draft_pointer import (
    clear_ticket_draft,
    get_ticket_draft,
    set_ticket_draft,
)
from app.services.client_phase11.ticket_enrichment import enrich_ticket_body
from app.services.client_phase11.ticket_executor import execute_open_support_ticket
from app.services.client_phase11.ticket_intent import (
    fallback_plan_from_message,
    is_support_workspace,
    is_ticket_confirmation_followup,
    is_tracking_clarification_followup,
    is_user_cancellation,
    is_user_confirmation,
    list_my_tickets_message,
    ticket_confirmation_message,
    tracking_clarification_message,
)
from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.support_ticket_service import (
    normalize_ticket_category,
    normalize_ticket_priority,
    sanitize_support_text,
)
from app.utils.tracking_parser import is_plausible_tracking_number

logger = logging.getLogger(__name__)

_VALID_TASKS = frozenset({"open_support_ticket", "list_my_tickets", "conversation"})
_SUPPORT_TASKS = frozenset({"open_support_ticket", "list_my_tickets"})


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
        import json

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
    return code if code in {"fr", "en"} else "fr"


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
    return (row.message_text or "").strip() if row else None


def _turn_result(reply: str, intent: str, *, llm_provider: str | None = "ollama") -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "agent_support",
        "intent": intent,
        "tracking_number": None,
        "llm_provider": llm_provider,
        "shipment": None,
        "export_download": None,
    }


def reconcile_plan(message: str, plan: dict[str, Any], *, lang: str) -> dict[str, Any]:
    answers = dict(plan.get("answers") or {})
    answers["category"] = normalize_ticket_category(str(answers.get("category") or "other"))
    answers["priority"] = normalize_ticket_priority(str(answers.get("priority") or "medium"))
    tn = str(answers.get("tracking_number") or "").strip() or extract_tracking_number(message or "")
    if tn and is_plausible_tracking_number(tn):
        answers["tracking_number"] = tn
    else:
        answers["tracking_number"] = ""
    subject = sanitize_support_text(str(answers.get("subject") or ""))[:200]
    body = sanitize_support_text(str(answers.get("message") or ""))[:4000]
    if not subject:
        subject = "Demande client via chat"
    if not body:
        body = (message or "").strip() or "Signalement via le chat client FedEx."
    answers["subject"] = subject
    answers["message"] = body
    plan["answers"] = answers

    if plan.get("task_type") == "open_support_ticket":
        if answers["category"] == "tracking" and not answers["tracking_number"]:
            plan["needs_clarification"] = True
            plan["ready_to_execute"] = False
            plan["clarification_question"] = plan.get("clarification_question") or tracking_clarification_message(lang)
    return plan


def _call_ollama_plan(
    message: str,
    *,
    history: str,
    ui_language: str | None,
    system_prompt: str = CLIENT_SUPPORT_ROUTER_PROMPT,
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
    logger.info("Phase 11 router non-JSON: %s", (raw or "")[:200])
    return None


def plan_support_task(
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

    if is_support_workspace(message):
        fb = fallback_plan_from_message(message, lang=lang)
        if fb and fb.get("ready_to_execute") and not fb.get("needs_clarification"):
            return reconcile_plan(message, fb, lang=lang)

    plan: dict[str, Any] | None = None
    ollama_failed = False

    try:
        plan = _call_ollama_plan(message, history=history, ui_language=ui_language)
    except LlmProviderError:
        ollama_failed = True
        logger.warning("Phase 11 router Ollama unavailable", exc_info=True)

    if plan and plan.get("task_type") in _SUPPORT_TASKS:
        return reconcile_plan(message, plan, lang=lang)

    if not ollama_failed and is_support_workspace(message):
        try:
            retry = _call_ollama_plan(
                message,
                history=history,
                ui_language=ui_language,
                system_prompt=CLIENT_SUPPORT_ROUTER_RETRY_PROMPT,
            )
            if retry and retry.get("task_type") in _SUPPORT_TASKS:
                return reconcile_plan(message, retry, lang=lang)
        except LlmProviderError:
            logger.warning("Phase 11 router Ollama retry unavailable", exc_info=True)

    if is_support_workspace(message):
        fallback = fallback_plan_from_message(message, lang=lang)
        if fallback:
            return reconcile_plan(message, fallback, lang=lang)
    return None


def _confirmation_followup_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    ui_language: str | None,
) -> dict[str, Any] | None:
    last_bot = _last_bot_message_text(db, session.id)
    if not last_bot or not is_ticket_confirmation_followup(last_bot):
        return None

    lang = _lang(ui_language, user)
    if is_user_cancellation(message):
        clear_ticket_draft(session.id)
        if lang == "en":
            return _turn_result("Ticket creation cancelled.", "support_ticket_cancelled")
        return _turn_result("Création du ticket annulée.", "support_ticket_cancelled")

    if not is_user_confirmation(message):
        return None

    draft = get_ticket_draft(session.id)
    if draft is None:
        if lang == "en":
            return _turn_result(
                "I no longer have the ticket draft. Please describe your issue again.",
                "support_ticket_draft_expired",
            )
        return _turn_result(
            "Je n'ai plus le brouillon du ticket. Décrivez à nouveau votre problème.",
            "support_ticket_draft_expired",
        )

    outcome = execute_open_support_ticket(
        db, user=user, session_id=session.id, draft=draft, lang=lang
    )
    return _turn_result(outcome["reply"], outcome["intent"])


def _clarification_followup_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    last_bot = _last_bot_message_text(db, session.id)
    if not last_bot or not is_tracking_clarification_followup(last_bot):
        return None

    lang = _lang(ui_language, user)
    tn = extract_tracking_number(message or "")
    if not tn or not is_plausible_tracking_number(tn):
        return _turn_result(tracking_clarification_message(lang), "support_ticket_clarify")

    draft = get_ticket_draft(session.id)
    if draft is None:
        answers = {
            "subject": "Demande client via chat",
            "message": (message or "").strip(),
            "category": "tracking",
            "priority": "medium",
            "tracking_number": tn,
        }
    else:
        answers = {
            "subject": draft.subject,
            "message": draft.message,
            "category": draft.category,
            "priority": draft.priority,
            "tracking_number": tn,
        }

    enriched, resolved_tn = enrich_ticket_body(
        db,
        user=user,
        session=session,
        message=message,
        body=str(answers.get("message") or ""),
        tracking_number=tn,
        exclude_message_id=exclude_message_id,
    )
    plan = reconcile_plan(
        message,
        {
            "task_type": "open_support_ticket",
            "assistant_intro": "",
            "answers": {**answers, "message": enriched, "tracking_number": resolved_tn or tn},
            "ready_to_execute": False,
            "needs_clarification": False,
            "clarification_question": "",
        },
        lang=lang,
    )
    return _present_draft_or_execute(db, user, session, plan, lang=lang)


def _present_draft_or_execute(
    db: Session,
    user: User,
    session: ChatSession,
    plan: dict[str, Any],
    *,
    lang: str,
) -> dict[str, Any]:
    answers = dict(plan.get("answers") or {})
    set_ticket_draft(
        session.id,
        {
            "subject": answers.get("subject"),
            "message": answers.get("message"),
            "category": answers.get("category"),
            "priority": answers.get("priority"),
            "tracking_number": answers.get("tracking_number"),
        },
    )
    if plan.get("ready_to_execute"):
        draft = get_ticket_draft(session.id)
        if draft is not None:
            outcome = execute_open_support_ticket(
                db, user=user, session_id=session.id, draft=draft, lang=lang
            )
            return _turn_result(outcome["reply"], outcome["intent"])

    intro = str(plan.get("assistant_intro") or "").strip()
    confirm = ticket_confirmation_message(
        subject=str(answers.get("subject") or ""),
        message=str(answers.get("message") or ""),
        category=str(answers.get("category") or "other"),
        priority=str(answers.get("priority") or "medium"),
        tracking_number=str(answers.get("tracking_number") or "") or None,
        lang=lang,
    )
    reply = f"{intro}\n\n{confirm}".strip() if intro else confirm
    return _turn_result(reply, "support_ticket_draft")


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
    lang = _lang(ui_language, user)

    if task == "list_my_tickets":
        intro = str(plan.get("assistant_intro") or "").strip()
        body = list_my_tickets_message(lang)
        reply = f"{intro}\n\n{body}".strip() if intro else body
        return _turn_result(reply, "list_my_tickets")

    if task != "open_support_ticket":
        return _turn_result("", "conversation")

    if plan.get("needs_clarification") and plan.get("clarification_question"):
        answers = dict(plan.get("answers") or {})
        set_ticket_draft(
            session.id,
            {
                "subject": answers.get("subject"),
                "message": answers.get("message"),
                "category": answers.get("category"),
                "priority": answers.get("priority"),
                "tracking_number": answers.get("tracking_number"),
            },
        )
        return _turn_result(plan["clarification_question"], "support_ticket_clarify")

    answers = dict(plan.get("answers") or {})
    enriched, tn = enrich_ticket_body(
        db,
        user=user,
        session=session,
        message=message,
        body=str(answers.get("message") or ""),
        tracking_number=str(answers.get("tracking_number") or "") or None,
        exclude_message_id=exclude_message_id,
    )
    answers["message"] = enriched
    if tn:
        answers["tracking_number"] = tn
    plan = reconcile_plan(message, {**plan, "answers": answers}, lang=lang)

    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return _turn_result(plan["clarification_question"], "support_ticket_clarify")

    return _present_draft_or_execute(db, user, session, plan, lang=lang)


def try_client_support_ticket_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    if not router_enabled() or not has_support_ticket_capability():
        return None

    confirm_turn = _confirmation_followup_turn(
        db, user, session, message, ui_language=ui_language
    )
    if confirm_turn is not None:
        return confirm_turn

    clarify_turn = _clarification_followup_turn(
        db,
        user,
        session,
        message,
        exclude_message_id=exclude_message_id,
        ui_language=ui_language,
    )
    if clarify_turn is not None:
        return clarify_turn

    if not is_support_workspace(message):
        return None

    plan = plan_support_task(
        db,
        user,
        session,
        message,
        exclude_message_id=exclude_message_id,
        ui_language=ui_language,
    )
    if plan is None or plan.get("task_type") == "conversation":
        return None

    executed = _execute_plan(
        db,
        user,
        session,
        plan,
        message,
        exclude_message_id=exclude_message_id,
        ui_language=ui_language,
    )
    if executed.get("intent") == "conversation" and not executed.get("reply"):
        return None
    return executed
