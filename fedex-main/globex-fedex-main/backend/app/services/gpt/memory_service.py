"""Mémoire conversationnelle court et long terme par GPT."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gpt_definition import GptDefinition, UserGptMemory
from app.services.chat_session_context import build_conversation_history_for_llm
from app.services.llm.providers import normalize_lang_code


def load_gpt_memory(db: Session, *, user_id: int, gpt_id: int) -> UserGptMemory | None:
    return db.scalar(
        select(UserGptMemory).where(
            UserGptMemory.user_id == user_id,
            UserGptMemory.gpt_id == gpt_id,
        )
    )


def get_or_create_memory(db: Session, *, user_id: int, gpt_id: int) -> UserGptMemory:
    row = load_gpt_memory(db, user_id=user_id, gpt_id=gpt_id)
    if row is None:
        row = UserGptMemory(user_id=user_id, gpt_id=gpt_id, facts_json="{}")
        db.add(row)
        db.flush()
    return row


def parse_facts(raw: str | None) -> dict[str, str]:
    if not (raw or "").strip():
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v is not None}
    except json.JSONDecodeError:
        pass
    return {}


def update_language_preference(
    db: Session,
    *,
    user_id: int,
    gpt_id: int,
    language: str,
) -> None:
    mem = get_or_create_memory(db, user_id=user_id, gpt_id=gpt_id)
    facts = parse_facts(mem.facts_json)
    facts["preferred_response_language"] = normalize_lang_code(language)
    mem.facts_json = json.dumps(facts, ensure_ascii=False)


def detect_language_preference(message: str) -> str | None:
    """Détecte une demande explicite de langue (légitime)."""
    text = (message or "").strip().lower()
    if not text or len(text) > 80:
        return None
    fr_triggers = (
        "en français",
        "en francais",
        "réponds en français",
        "reponds en francais",
        "répond en français",
        "repond en francais",
        "parle français",
        "parle francais",
        "français svp",
        "francais svp",
    )
    en_triggers = (
        "in english",
        "english please",
        "reply in english",
        "speak english",
    )
    ar_triggers = (
        "en arabe",
        "بالعربية",
        "in arabic",
        "arabic please",
        "réponds en arabe",
        "reponds en arabe",
        "réponds toujours en arabe",
    )
    es_triggers = (
        "en español",
        "en espanol",
        "habla español",
        "habla espanol",
        "habla solamente en español",
        "reply in spanish",
        "in spanish",
    )
    de_triggers = (
        "auf deutsch",
        "in german",
        "antworte auf deutsch",
        "reply in german",
    )
    switch_triggers = (
        "désormais en",
        "desormais en",
        "from now on in",
        "answer in",
        "reply in",
        "réponds en",
        "reponds en",
        "responde en",
        "please answer in",
    )
    if any(t in text for t in fr_triggers):
        return "fr"
    if any(t in text for t in en_triggers):
        return "en"
    if any(t in text for t in ar_triggers):
        return "ar"
    if any(t in text for t in es_triggers):
        return "es"
    if any(t in text for t in de_triggers):
        return "de"
    if any(t in text for t in switch_triggers):
        if "français" in text or "francais" in text or "french" in text:
            return "fr"
        if "english" in text or "anglais" in text:
            return "en"
        if "español" in text or "espanol" in text or "spanish" in text:
            return "es"
        if "arabe" in text or "arabic" in text or "عرب" in text:
            return "ar"
        if "deutsch" in text or "german" in text or "allemand" in text:
            return "de"
    return None


def build_memory_context(
    db: Session,
    *,
    gpt: GptDefinition,
    user_id: int | None,
    session_id: int | None,
    exclude_message_id: int | None = None,
) -> dict[str, Any]:
    """Assemble mémoire court terme + facts long terme."""
    short_history = ""
    if session_id is not None:
        short_history = build_conversation_history_for_llm(
            db,
            session_id=session_id,
            exclude_message_id=exclude_message_id,
            limit=gpt.memory_short_window,
        )

    long_facts: dict[str, str] = {}
    session_summary = ""
    if user_id is not None and gpt.memory_long_term_enabled:
        mem = load_gpt_memory(db, user_id=user_id, gpt_id=gpt.id)
        if mem:
            long_facts = parse_facts(mem.facts_json)
            session_summary = (mem.session_summary or "").strip()

    return {
        "short_history": short_history,
        "long_facts": long_facts,
        "session_summary": session_summary,
    }


def format_memory_block(ctx: dict[str, Any]) -> str:
    parts: list[str] = []
    summary = (ctx.get("session_summary") or "").strip()
    if summary:
        parts.append(f"Résumé des conversations précédentes :\n{summary[:1500]}")
    facts: dict[str, str] = ctx.get("long_facts") or {}
    if facts:
        lines = [f"- {k}: {v}" for k, v in facts.items()]
        parts.append("Préférences et faits mémorisés :\n" + "\n".join(lines))
    history = (ctx.get("short_history") or "").strip()
    if history:
        parts.append(
            "Historique récent de cette session (contexte fiable) :\n" + history[:3000]
        )
    return "\n\n".join(parts) if parts else "Premier échange ou session sans historique."
