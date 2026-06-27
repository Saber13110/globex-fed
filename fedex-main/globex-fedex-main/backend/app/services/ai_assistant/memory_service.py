"""Mémoire conversationnelle — session + résumé + préférences."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.gpt_definition import GptDefinition
from app.models.user import User
from app.services.gpt.memory_service import (
    build_memory_context,
    format_memory_block,
    get_or_create_memory,
    parse_facts,
    update_language_preference,
)


def load_session_memory(copilot_state: dict[str, Any] | None) -> dict[str, Any]:
    state = copilot_state or {}
    return {
        "preferred_language": state.get("preferred_language"),
        "summary": state.get("conversation_summary") or "",
        "last_tools": state.get("last_tools_used") or [],
        "last_intent": state.get("last_intent"),
    }


def merge_session_after_turn(
    copilot_state: dict[str, Any] | None,
    *,
    language: str,
    tools_used: list[str],
    intent: str,
    reply_summary: str,
    entity_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = dict(copilot_state or {})
    state["preferred_language"] = language
    state["last_tools_used"] = tools_used
    state["last_intent"] = intent
    prev = (state.get("conversation_summary") or "").strip()
    snippet = reply_summary[:200]
    if snippet and snippet not in prev:
        state["conversation_summary"] = f"{prev}\n- {snippet}".strip()[-1500:]
    if entity_updates:
        state.update(entity_updates)
    return state


def build_agent_memory_block(
    db: Session,
    *,
    gpt: GptDefinition,
    user: User,
    session_id: int | None,
    copilot_state: dict[str, Any] | None,
) -> str:
    ctx = build_memory_context(
        db, gpt=gpt, user_id=user.id, session_id=session_id,
    )
    session = load_session_memory(copilot_state)
    parts = [format_memory_block(ctx)]
    if session.get("summary"):
        parts.append(f"Résumé session courante :\n{session['summary'][:800]}")
    facts = ctx.get("long_facts") or {}
    lang = session.get("preferred_language") or facts.get("preferred_response_language")
    if lang:
        parts.append(f"Langue active mémorisée : {lang}")
    return "\n\n".join(p for p in parts if p)


def persist_language_preference(
    db: Session,
    *,
    user: User,
    gpt: GptDefinition,
    language: str,
) -> None:
    update_language_preference(
        db, user_id=user.id, gpt_id=gpt.id, language=language,
    )
    mem = get_or_create_memory(db, user_id=user.id, gpt_id=gpt.id)
    facts = parse_facts(mem.facts_json)
    facts["preferred_language"] = language
    mem.facts_json = json.dumps(facts, ensure_ascii=False)
    db.flush()
