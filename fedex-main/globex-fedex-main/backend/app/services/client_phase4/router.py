"""
Routeur Phase 4 — sessions (list / summarize).

Branchement unique depuis chatbot_service AVANT early_turn PDF/Excel.
Requiert CLIENT_AGENT_ROUTER_ENABLED=true et cap sessions dans CLIENT_AGENT_CAPABILITIES.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_session_context import build_conversation_history_for_llm
from app.services.client_phase4.capabilities import has_sessions_capability, router_enabled
from app.services.client_phase4.router_prompt import (
    CLIENT_SESSIONS_ROUTER_PROMPT,
    CLIENT_SESSIONS_ROUTER_RETRY_PROMPT,
)
from app.services.client_phase4.session_executor import execute_list_sessions, execute_summarize_session
from app.services.client_phase4.session_reference import (
    enrich_summarize_answers,
    parse_session_reference,
    parse_summarize_selection,
)
from app.services.client_phase4.session_service import format_session_line, list_user_sessions
from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan

logger = logging.getLogger(__name__)

_VALID_TASKS = frozenset({"list_sessions", "summarize_session", "conversation"})
_SESSION_TASKS = frozenset({"list_sessions", "summarize_session"})

_TRACKING_IN_MESSAGE = re.compile(
    r"\b(\d{10,15}|colis|tracking|fedex|livraison|expédition|expedition|numéro de suivi)\b",
    re.I,
)

_SUMMARIZE_RE = re.compile(
    r"\b(resume|resumer|recap|synthese)\b",
    re.I,
)
_LIST_VERB_RE = re.compile(
    r"\b(donne|donner|montre|montrez|liste|lister|affiche|affichez|voir|quelles)\b",
    re.I,
)
_CONV_RE = re.compile(r"\b(conversations?|discussions?|chats?)\b", re.I)
_RECENT_PLURAL_RE = re.compile(
    r"\b(conversations?|discussions?)\b.*\b(recent|recents|recentes)\b",
    re.I,
)
_AMBIGUOUS_SUMMARIZE_MARKERS = (
    "plusieurs conversations correspondent",
    "which one should i summarize",
    "عدة محادثات تطابق",
)
_NUMBERED_SESSION_LINE = re.compile(
    r"^\s*(\d+)\.\s+(.+?)\s*·\s*(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})",
    re.M,
)


def _normalize_message_text(message: str) -> str:
    raw = (message or "").strip().lower()
    folded = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _looks_like_summarize_request(message: str) -> bool:
    text = _normalize_message_text(message)
    if _SUMMARIZE_RE.search(text):
        return True
    if "de quoi" in text and any(
        w in text for w in ("parle", "echange", "discussion", "conversation")
    ):
        return True
    if any(w in text for w in ("synthese", "recapitulatif")):
        return True
    ref = parse_session_reference(message)
    if ref.get("session_updated_hint"):
        if any(w in text for w in ("de quoi", "parle", "sujet", "resume", "resumer", "recap")):
            return True
    if ref.get("session_hint") and ref.get("session_time_hint"):
        if any(w in text for w in ("de quoi", "parle", "sujet", "resume", "resumer", "recap")):
            return True
    return False


def _references_past_session(message: str) -> bool:
    ref = parse_session_reference(message)
    if ref.get("list_index") or ref.get("session_id") or ref.get("session_updated_hint"):
        return True
    if ref.get("session_hint") and (
        ref.get("session_updated_hint") or ref.get("session_time_hint")
    ):
        return True
    return False


def _is_pure_list_request(message: str) -> bool:
    return _looks_like_list_request(message) and not _references_past_session(message)


def _looks_like_list_request(message: str) -> bool:
    if _looks_like_summarize_request(message):
        return False
    text = _normalize_message_text(message)
    if _LIST_VERB_RE.search(text) and _CONV_RE.search(text):
        return True
    if _RECENT_PLURAL_RE.search(text):
        return True
    return False


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


def _reconcile_sessions_plan(message: str, plan: dict[str, Any]) -> dict[str, Any]:
    task = plan.get("task_type")
    ref = parse_session_reference(message)

    if task == "list_sessions" and _references_past_session(message):
        if (
            _looks_like_summarize_request(message)
            or ref.get("session_updated_hint")
            or ref.get("session_time_hint")
        ):
            return {
                **plan,
                "task_type": "summarize_session",
                "answers": enrich_summarize_answers(message, dict(plan.get("answers") or {})),
                "ready_to_execute": True,
                "needs_clarification": False,
                "clarification_question": "",
            }

    if task == "summarize_session" and _is_pure_list_request(message):
        return {
            **plan,
            "task_type": "list_sessions",
            "answers": {},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }
    if task == "summarize_session":
        return {
            **plan,
            "answers": enrich_summarize_answers(message, dict(plan.get("answers") or {})),
        }
    return plan


def _is_session_workspace_message(message: str) -> bool:
    """Détecte si le message concerne l'espace conversations (retry / fallback offline)."""
    text = (message or "").strip().lower()
    if not text:
        return False
    if _TRACKING_IN_MESSAGE.search(text):
        conv_words = ("conversation", "discussion", "échange", "echange", "chat", "parlé", "parle")
        if not any(w in text for w in conv_words):
            return False
    workspace_hints = (
        "conversation",
        "discussions",
        "discussion",
        "échange",
        "echanges",
        "chats",
        "de quoi on a parlé",
        "de quoi parle",
        "de quoi on parle",
        "conversations passées",
        "conversations passees",
        "dernière discussion",
        "derniere discussion",
        "mes discussions",
        "mes conversations",
        "liste des conversations",
        "historique de chat",
        "résume",
        "resumer",
        "résumer",
        "synthèse",
        "synthese",
        "récap",
        "recap",
    )
    return any(h in text for h in workspace_hints) or _looks_like_summarize_request(message)


def _deterministic_summarize_plan(message: str) -> dict[str, Any] | None:
    if not _looks_like_summarize_request(message) or not _references_past_session(message):
        return None
    return {
        "task_type": "summarize_session",
        "assistant_intro": "",
        "answers": enrich_summarize_answers(message, {}),
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }


def _fallback_plan_from_message(message: str) -> dict[str, Any] | None:
    """Repli offline uniquement quand Ollama est indisponible."""
    if not _is_session_workspace_message(message):
        return None

    if _is_pure_list_request(message):
        return {
            "task_type": "list_sessions",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }

    ref = parse_session_reference(message)
    answers: dict[str, Any] = {}
    if ref.get("list_index"):
        answers["list_index"] = ref["list_index"]
    if ref.get("session_hint"):
        answers["session_hint"] = ref["session_hint"]
    if ref.get("session_id"):
        answers["session_id"] = ref["session_id"]

    if not answers:
        text = _normalize_message_text(message)
        scope = "current"
        if any(w in text for w in ("derniere", "recente", "passees", "passee")):
            scope = "last"
        if any(
            w in text
            for w in (
                "notre conversation",
                "cette conversation",
                "cette discussion",
                "cet echange",
                "ici",
                "actuelle",
            )
        ):
            scope = "current"
        answers["scope"] = scope

    answers = enrich_summarize_answers(message, answers)

    return {
        "task_type": "summarize_session",
        "assistant_intro": "",
        "answers": answers,
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }


def _is_ambiguous_summarize_prompt(bot_text: str) -> bool:
    norm = _normalize_message_text(bot_text)
    return any(marker in norm for marker in _AMBIGUOUS_SUMMARIZE_MARKERS)


def _parse_numbered_sessions_from_listing(bot_text: str) -> list[dict[str, Any]]:
    from datetime import datetime, timezone

    rows: list[dict[str, Any]] = []
    for match in _NUMBERED_SESSION_LINE.finditer(bot_text or ""):
        try:
            idx = int(match.group(1))
            hint = (match.group(2) or "").strip().lower()
            date_parts = match.group(3).split("/")
            day = int(date_parts[0])
            month = int(date_parts[1])
            year = int(date_parts[2])
            time_parts = match.group(4).split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            updated = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except (TypeError, ValueError, IndexError):
            continue
        rows.append(
            {
                "list_index": idx,
                "session_hint": hint,
                "session_updated_hint": updated,
            }
        )
    return rows


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


def _summarize_followup_plan(
    db: Session,
    session_id: int,
    message: str,
) -> dict[str, Any] | None:
    """Réponse courte après clarification « Laquelle résumer ? » — sans rappeler Ollama."""
    last_bot = _last_bot_message_text(db, session_id)
    is_ambiguous = bool(last_bot and _is_ambiguous_summarize_prompt(last_bot))
    ref = parse_session_reference(message)

    if is_ambiguous:
        answers: dict[str, Any] = {}
        selection = parse_summarize_selection(message)
        if selection is not None:
            for row in _parse_numbered_sessions_from_listing(last_bot or ""):
                if row.get("list_index") == selection:
                    answers = dict(row)
                    break
            if not answers:
                answers["list_index"] = selection
        if ref.get("session_hint"):
            answers.setdefault("session_hint", ref["session_hint"])
        if ref.get("session_updated_hint"):
            answers.setdefault("session_updated_hint", ref["session_updated_hint"])
        if ref.get("session_time_hint"):
            answers.setdefault("session_time_hint", ref["session_time_hint"])
        if not _has_summarize_followup_target(answers):
            return None
        return {
            "task_type": "summarize_session",
            "assistant_intro": "",
            "answers": enrich_summarize_answers(message, answers),
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }

    if ref.get("session_hint") and (
        ref.get("session_updated_hint") or ref.get("session_time_hint")
    ):
        return {
            "task_type": "summarize_session",
            "assistant_intro": "",
            "answers": enrich_summarize_answers(message, {}),
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }

    if ref.get("list_index") and re.search(
        r"(?:conversation|discussion|échange|echange|chat)\s*:\s*\d{1,2}\s*[.)]",
        message,
        re.I,
    ):
        return {
            "task_type": "summarize_session",
            "assistant_intro": "",
            "answers": enrich_summarize_answers(message, {}),
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }
    if ref.get("list_index") and re.search(r"(?:^|[\s:])\d{1,2}\s*[.)]\s+", message):
        return {
            "task_type": "summarize_session",
            "assistant_intro": "",
            "answers": enrich_summarize_answers(message, {}),
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }

    return None


def _has_summarize_followup_target(answers: dict[str, Any]) -> bool:
    return bool(
        answers.get("list_index")
        or answers.get("session_id")
        or (
            answers.get("session_hint")
            and (
                answers.get("session_updated_hint") or answers.get("session_time_hint")
            )
        )
    )


def _session_titles_context(db: Session, user_id: int, lang: str) -> str:
    sessions = list_user_sessions(db, user_id=user_id, limit=10)
    if not sessions:
        return ""
    lines = []
    for i, s in enumerate(sessions, start=1):
        lines.append(f"id={s.id} · {format_session_line(s, index=i, lang=lang)}")
    return "\n".join(lines)


def _call_ollama_sessions_plan(
    message: str,
    *,
    system_prompt: str,
    history: str,
    titles: str,
    ui_language: str | None,
) -> dict[str, Any] | None:
    raw = call_ollama_agent_plan(
        message,
        system_prompt=system_prompt,
        conversation_history=history,
        session_titles=titles,
        ui_language=ui_language,
    )
    data = _parse_json_object(raw)
    if data:
        return _plan_from_data(data)
    logger.info("Phase 4 router non-JSON: %s", (raw or "")[:200])
    return None


def plan_sessions_task(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    lang = (ui_language or user.preferred_language or "fr").lower()[:2]
    history = build_conversation_history_for_llm(
        db,
        session_id=session.id,
        exclude_message_id=exclude_message_id,
        limit=4,
    )
    titles = _session_titles_context(db, user.id, lang)

    plan: dict[str, Any] | None = None
    ollama_failed = False

    try:
        plan = _call_ollama_sessions_plan(
            message,
            system_prompt=CLIENT_SESSIONS_ROUTER_PROMPT,
            history=history,
            titles=titles,
            ui_language=ui_language,
        )
    except LlmProviderError:
        ollama_failed = True
        logger.warning("Phase 4 router Ollama unavailable", exc_info=True)

    if plan and plan.get("task_type") in _SESSION_TASKS:
        return _reconcile_sessions_plan(message, plan)

    if not ollama_failed and _is_session_workspace_message(message):
        try:
            retry_plan = _call_ollama_sessions_plan(
                message,
                system_prompt=CLIENT_SESSIONS_ROUTER_RETRY_PROMPT,
                history=history,
                titles=titles,
                ui_language=ui_language,
            )
            if retry_plan and retry_plan.get("task_type") in _SESSION_TASKS:
                logger.info("Phase 4 router retry plan task=%s", retry_plan.get("task_type"))
                return _reconcile_sessions_plan(message, retry_plan)
        except LlmProviderError:
            ollama_failed = True
            logger.warning("Phase 4 router Ollama retry unavailable", exc_info=True)

    if ollama_failed and _is_session_workspace_message(message):
        fallback = _fallback_plan_from_message(message)
        if fallback:
            logger.info("Phase 4 router offline fallback task=%s", fallback.get("task_type"))
            return fallback

    det = _deterministic_summarize_plan(message)
    if det:
        logger.info("Phase 4 router deterministic summarize plan")
        return det

    return None


def _turn_result(
    reply: str,
    intent: str,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "agent_sessions",
        "intent": intent,
        "tracking_number": None,
        "llm_provider": "ollama",
        "shipment": None,
        "export_download": None,
    }


def try_client_sessions_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """
    Tente le routeur sessions. Retourne un dict compatible _apply_early_export_turn
    ou None pour laisser le flux Phase 2/3 inchangé.
    """
    if not router_enabled() or not has_sessions_capability():
        logger.debug(
            "Phase 4 sessions skipped router=%s cap_sessions=%s",
            router_enabled(),
            has_sessions_capability(),
        )
        return None

    plan = _summarize_followup_plan(db, session.id, message)
    if plan is None:
        plan = plan_sessions_task(
            db,
            user,
            session,
            message,
            exclude_message_id=exclude_message_id,
            ui_language=ui_language,
        )
    if plan is None:
        plan = _deterministic_summarize_plan(message)
    if plan is None:
        return None

    task = plan["task_type"]
    if task == "conversation":
        return None

    intro = plan.get("assistant_intro") or ""
    if plan.get("needs_clarification") and plan.get("clarification_question"):
        return _turn_result(plan["clarification_question"], task)

    if task == "list_sessions":
        reply = execute_list_sessions(
            db,
            user,
            ui_language=ui_language,
            assistant_intro=intro,
        )
        return _turn_result(reply, "list_sessions")

    if task == "summarize_session":
        answers = enrich_summarize_answers(message, dict(plan.get("answers") or {}))
        reply, _needs_clarification = execute_summarize_session(
            db,
            user,
            current_session_id=session.id,
            answers=answers,
            ui_language=ui_language,
            assistant_intro=intro,
        )
        return _turn_result(reply, "summarize_session")

    return None
