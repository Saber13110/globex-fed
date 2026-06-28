"""

Routeur Phase 5 — notifications (list / filter / summarize / PDF).



Branchement depuis chatbot_service après try_client_sessions_turn.

Requiert CLIENT_AGENT_ROUTER_ENABLED=true et cap notifications.

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

from app.services.client_phase5.capabilities import has_notifications_capability, router_enabled

from app.services.client_phase5.notification_executor import (

    execute_mark_all_read,

    execute_notifications_query,

)

from app.services.client_phase5.notification_filters import (

    apply_read_intent_to_plan,

    build_list_read_plan,

    build_mark_all_read_plan,

    extract_notification_limit,

    fallback_plan_from_message,

    is_notification_workspace,

    is_read_clarification_followup,

    params_from_answers,

    parse_read_clarification_reply,

    reconcile_notification_plan,

)

from app.services.client_phase5.router_prompt import (

    CLIENT_NOTIFICATIONS_ROUTER_PROMPT,

    CLIENT_NOTIFICATIONS_ROUTER_RETRY_PROMPT,

)

from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan



logger = logging.getLogger(__name__)



_VALID_TASKS = frozenset({"notifications_query", "notifications_mark_all_read", "conversation"})

_NOTIFICATION_TASKS = frozenset({"notifications_query", "notifications_mark_all_read"})





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





def _call_ollama_notifications_plan(

    message: str,

    *,

    history: str,

    ui_language: str | None,

    system_prompt: str = CLIENT_NOTIFICATIONS_ROUTER_PROMPT,

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

    logger.info("Phase 5 router non-JSON: %s", (raw or "")[:200])

    return None





def _log_final_plan(plan: dict[str, Any], *, source: str) -> None:

    answers = plan.get("answers") or {}

    logger.info(

        "Phase 5 plan task=%s limit=%s section=%s mode=%s source=%s",

        plan.get("task_type"),

        answers.get("limit"),

        answers.get("section"),

        answers.get("mode"),

        source,

    )





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





def _finalize_plan(message: str, plan: dict[str, Any], *, lang: str) -> dict[str, Any]:

    if plan.get("task_type") == "notifications_query" and not plan.get("needs_clarification"):

        plan = reconcile_notification_plan(message, plan)

    return apply_read_intent_to_plan(message, plan, lang=lang)





def _read_clarification_followup_plan(

    db: Session,

    session_id: int,

    message: str,

    *,

    lang: str,

) -> dict[str, Any] | None:

    last_bot = _last_bot_message_text(db, session_id)

    if not last_bot or not is_read_clarification_followup(last_bot):

        return None

    choice = parse_read_clarification_reply(message)

    if choice == "list_read":

        return build_list_read_plan(lang)

    if choice == "mark_all":

        return build_mark_all_read_plan()

    return None





def plan_notifications_task(

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

        plan = _call_ollama_notifications_plan(message, history=history, ui_language=ui_language)

    except LlmProviderError:

        ollama_failed = True

        logger.warning("Phase 5 router Ollama unavailable", exc_info=True)



    if plan and plan.get("task_type") in _NOTIFICATION_TASKS:

        finalized = _finalize_plan(message, plan, lang=lang)

        _log_final_plan(finalized, source="ollama")

        return finalized



    if not ollama_failed and is_notification_workspace(message):

        try:

            retry_plan = _call_ollama_notifications_plan(

                message,

                history=history,

                ui_language=ui_language,

                system_prompt=CLIENT_NOTIFICATIONS_ROUTER_RETRY_PROMPT,

            )

            if retry_plan and retry_plan.get("task_type") in _NOTIFICATION_TASKS:

                finalized = _finalize_plan(message, retry_plan, lang=lang)

                _log_final_plan(finalized, source="retry")

                return finalized

        except LlmProviderError:

            ollama_failed = True

            logger.warning("Phase 5 router Ollama retry unavailable", exc_info=True)



    if ollama_failed and is_notification_workspace(message):

        fallback = fallback_plan_from_message(message, lang=lang)

        if fallback:

            _log_final_plan(fallback, source="fallback")

            logger.info("Phase 5 router offline fallback")

            return fallback



    if is_notification_workspace(message) and (

        plan is None or plan.get("task_type") == "conversation"

    ):

        fallback = fallback_plan_from_message(message, lang=lang)

        if fallback:

            _log_final_plan(fallback, source="fallback")

            return fallback



    return None





def _turn_result(

    reply: str,

    intent: str,

    export_download: dict[str, Any] | None = None,

) -> dict[str, Any]:

    return {

        "reply": reply,

        "source": "agent_notifications",

        "intent": intent,

        "tracking_number": None,

        "llm_provider": "ollama",

        "shipment": None,

        "export_download": export_download,

    }





def _execute_plan(

    db: Session,

    user: User,

    session: ChatSession,

    plan: dict[str, Any],

    message: str,

    *,

    ui_language: str | None,

) -> dict[str, Any]:

    task = plan.get("task_type")

    if task == "conversation":

        return None  # type: ignore[return-value]



    if plan.get("needs_clarification") and plan.get("clarification_question"):

        return _turn_result(plan["clarification_question"], task or "notifications_query")



    lang = _lang(ui_language, user)



    if task == "notifications_mark_all_read":

        reply = execute_mark_all_read(db, user.id, lang=lang)

        return _turn_result(reply, "notifications_mark_all_read")



    intro = plan.get("assistant_intro") or ""

    params = params_from_answers(dict(plan.get("answers") or {}))

    explicit_n = extract_notification_limit(message)

    if not intro.strip() and explicit_n and params.mode == "list":

        if lang == "en":

            intro = f"Here are your {explicit_n} most recent notifications."

        else:

            intro = f"Voici vos {explicit_n} notifications les plus récentes."

    reply, export_download = execute_notifications_query(

        db,

        user,

        session,

        params,

        message=message,

        ui_language=ui_language,

        assistant_intro=intro,

    )

    intent = "export_notifications_pdf" if export_download else "notifications_query"

    return _turn_result(reply, intent, export_download=export_download)





def try_client_notifications_turn(

    db: Session,

    user: User,

    session: ChatSession,

    message: str,

    exclude_message_id: int | None,

    ui_language: str | None,

) -> dict[str, Any] | None:

    """

    Tente le routeur notifications. Retourne un dict compatible _apply_early_export_turn

    ou None pour laisser le flux Phase 2/3 inchangé.

    """

    if not router_enabled() or not has_notifications_capability():

        return None



    lang = _lang(ui_language, user)

    followup = _read_clarification_followup_plan(db, session.id, message, lang=lang)

    if followup is not None:

        return _execute_plan(db, user, session, followup, message, ui_language=ui_language)



    if not is_notification_workspace(message):

        return None



    plan = plan_notifications_task(

        db,

        user,

        session,

        message,

        exclude_message_id=exclude_message_id,

        ui_language=ui_language,

    )

    if plan is None:

        return None



    return _execute_plan(db, user, session, plan, message, ui_language=ui_language)


