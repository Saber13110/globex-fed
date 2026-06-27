"""Orchestrateur GPT — pipeline unifié intention → RAG → mémoire → prompt → Gemini."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gpt_definition import GptDefinition
from app.services.gpt.follow_up_context import expand_follow_up_message
from app.services.gpt.knowledge_service import (
    build_attachment_context,
    format_knowledge_block,
    list_knowledge_inventory,
    retrieve_knowledge,
    summarize_latest_document,
)
from app.services.gpt.memory_service import (
    build_memory_context,
    detect_language_preference,
    format_memory_block,
    update_language_preference,
)
from app.services.gpt.intent_classifier import (
    INTENT_ADMIN_AGENTS,
    INTENT_ADMIN_USERS,
    INTENT_CAPABILITIES,
    INTENT_KNOWLEDGE,
    classify_intent,
)
from app.services.gpt.model_gateway import generate_with_context
from app.services.gpt.prompt_composer import build_gpt_user_payload
from app.services.gpt.rag_profiler import RagProfile
from app.services.llm.providers import normalize_lang_code, resolve_ui_language

logger = logging.getLogger(__name__)

SLUG_CLIENT = "fedex-client"
SLUG_ADMIN = "fedex-admin-ops"


@dataclass
class GptTurnResult:
    reply: str
    llm_provider: str
    gpt_slug: str
    knowledge_sources: list[str]
    intent: str = "general_question"


def load_gpt_by_slug(db: Session, slug: str) -> GptDefinition | None:
    return db.scalar(
        select(GptDefinition).where(GptDefinition.slug == slug, GptDefinition.is_active.is_(True))
    )


def run_gpt_turn(
    db: Session,
    *,
    gpt_slug: str,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    ui_language: str | None = None,
    profile_language: str | None = None,
    operational_context: str | None = None,
    fedex_context: str | None = None,
    response_preferences: str | None = None,
    preferred_name: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    exclude_message_id: int | None = None,
    conversation_history: str | None = None,
    attached_document_name: str | None = None,
    server_instruction: str | None = None,
) -> GptTurnResult:
    """
    Exécute un tour complet GPT :
    analyse → RAG → mémoire → composition prompt → Gemini.
    """
    gpt = load_gpt_by_slug(db, gpt_slug)
    if gpt is None:
        raise ValueError(f"GPT introuvable ou inactif : {gpt_slug}")

    lang = resolve_ui_language(ui_language, profile_language)

    # Préférence de langue explicite dans le message
    pref_lang = detect_language_preference(message)
    if pref_lang:
        lang = pref_lang
        if user_id is not None:
            update_language_preference(db, user_id=user_id, gpt_id=gpt.id, language=lang)

    memory_ctx = build_memory_context(
        db,
        gpt=gpt,
        user_id=user_id,
        session_id=session_id,
        exclude_message_id=exclude_message_id,
    )
    facts = memory_ctx.get("long_facts") or {}
    if facts.get("preferred_response_language"):
        lang = normalize_lang_code(facts["preferred_response_language"])

    classification = classify_intent(message, gpt_slug)
    intent = classification.intent
    profile = RagProfile(label=f"gpt_turn:{gpt_slug}")
    profile.add("intent_classify", detail=f"{intent} score={classification.score}")

    effective_message = expand_follow_up_message(message, conversation_history)

    rag_query = effective_message
    if attached_document_name:
        rag_query = f"{attached_document_name} {rag_query}"
    if (conversation_history or "").strip() and len((message or "").strip()) < 120:
        rag_query = f"{conversation_history.strip()[-800:]}\n{message}"
    if intent == INTENT_CAPABILITIES:
        rag_query = (
            f"{message} capacités copilot admin globex que pouvez-vous faire "
            "tracking support utilisateurs logs notifications synthèse"
        )

    rag_top_k = 5 if attached_document_name else 4
    rag_min_score = 1.0
    skip_vector = False
    if intent == INTENT_CAPABILITIES:
        rag_top_k = 3
        rag_min_score = 0.5
    elif intent == INTENT_KNOWLEDGE:
        rag_top_k = 3
        rag_min_score = 0.35
        skip_vector = True
    elif attached_document_name:
        rag_min_score = 0.35

    hits = retrieve_knowledge(
        db,
        gpt=gpt,
        query=rag_query,
        language=lang,
        top_k=rag_top_k,
        min_score=rag_min_score,
        skip_vector=skip_vector,
        profile=profile,
    )
    profile.add("knowledge_format")
    knowledge_text = format_knowledge_block(hits, intent=intent)
    if intent == INTENT_KNOWLEDGE:
        inventory = list_knowledge_inventory(db, gpt=gpt)
        if inventory:
            inv_lines = [
                "Inventaire documents indexés (source fiable) :",
                *(
                    f"- {item['filename']} ({item['collection']}, {item['indexed_at'][:10]})"
                    for item in inventory
                ),
            ]
        else:
            inv_lines = [
                "Inventaire documents indexés (source fiable) :",
                "- Aucun document indexé.",
            ]
        msg_l = (message or "").lower()
        if any(k in msg_l for k in ("dernier document", "résume le dernier", "resume le dernier")):
            latest = summarize_latest_document(db, gpt=gpt)
            if latest:
                inv_lines.append("")
                inv_lines.append(latest)
        knowledge_text = "\n".join(inv_lines) + "\n\n" + knowledge_text
    memory_text = format_memory_block(memory_ctx)

    op_ctx = operational_context
    if intent == INTENT_ADMIN_USERS and gpt_slug.startswith("fedex-admin"):
        op_ctx = (
            (operational_context or "")
            + "\n\nCONSIGNE SERVEUR : question comptes utilisateurs. "
            "Répondez avec les données OPERATIONAL_CONTEXT et KNOWLEDGE ; "
            "ne demandez jamais de numéro de suivi FedEx."
        )
    if intent == INTENT_ADMIN_AGENTS and gpt_slug.startswith("fedex-admin"):
        from app.services.admin_copilot_service import build_agent_catalog_context

        op_ctx = (
            (operational_context or "")
            + "\n\n"
            + build_agent_catalog_context()
            + "\n\nCONSIGNE SERVEUR : listez chaque agent copilot et son rôle (catalogue ci-dessus). "
            "Réponse directe, sans introduction générique."
        )
    elif intent == INTENT_CAPABILITIES and gpt_slug.startswith("fedex-admin"):
        op_ctx = (
            (operational_context or "")
            + "\n\nCONSIGNE SERVEUR : capacités générales du copilot. "
            "Répondez en prose naturelle et directe — pas de template mécanique."
        )

    server_instruction = (server_instruction or "").strip()
    if attached_document_name:
        attached_file_content, attachment_instruction = build_attachment_context(
            db,
            gpt=gpt,
            filename=attached_document_name,
            user_message=message,
        )
        if attachment_instruction:
            server_instruction = (
                f"{server_instruction}\n{attachment_instruction}".strip()
                if server_instruction
                else attachment_instruction
            )
    else:
        attached_file_content = ""

    profile.add("prompt_compose_start")
    payload = build_gpt_user_payload(
        effective_message,
        knowledge_text=knowledge_text,
        memory_text=memory_text,
        operational_context=op_ctx,
        fedex_context=fedex_context,
        response_preferences=response_preferences,
        preferred_name=preferred_name,
        ui_language=lang,
        conversation_history=conversation_history,
        server_instruction=server_instruction or None,
        attached_file_content=attached_file_content or None,
        max_chars=6000 if intent == INTENT_KNOWLEDGE else None,
    )
    profile.add("prompt_compose_done", detail=f"chars={len(payload)}")

    out_tokens = gpt.max_output_tokens
    if intent == INTENT_CAPABILITIES:
        out_tokens = max(out_tokens, 2048)
    elif intent == INTENT_KNOWLEDGE:
        out_tokens = min(out_tokens, 768)

    model_result = generate_with_context(
        gpt_slug=gpt_slug,
        user_payload=payload,
        ui_language=lang,
        max_output_tokens=out_tokens,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
        profile=profile,
    )
    profile.add("llm_complete", detail=f"provider={model_result.llm_provider}")
    logger.info("GPT turn profile: %s", profile.as_dict())

    sources = [h.source_ref or h.title for h in hits if h.source_ref or h.title]

    return GptTurnResult(
        reply=model_result.reply,
        llm_provider=model_result.llm_provider,
        gpt_slug=gpt_slug,
        knowledge_sources=sources,
        intent=intent,
    )


def _classify_intent(message: str, gpt_slug: str) -> str:
    """Rétrocompatibilité — délègue au classificateur détaillé."""
    return classify_intent(message, gpt_slug).intent
