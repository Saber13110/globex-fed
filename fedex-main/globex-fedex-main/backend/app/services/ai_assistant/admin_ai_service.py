"""Service principal AI Assistant admin — point d'entrée entreprise."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.agent_orchestrator import run_agent_graph
from app.services.ai_assistant.conversation_manager import resolve_language_for_turn
from app.services.ai_assistant.memory_service import merge_session_after_turn
from app.services.ai_assistant.response_builder import enrich_copilot_response
from app.services.gpt.memory_service import load_gpt_memory, parse_facts
from app.services.gpt.orchestrator import SLUG_ADMIN, load_gpt_by_slug

logger = logging.getLogger(__name__)


class AdminAiService:
    """Orchestrateur admin — agent multi-étapes avec outils, RAG et validation."""

    @staticmethod
    def run_turn(
        db: Session,
        admin: User,
        message: str,
        *,
        analysis_mode: bool = True,
        operational_context: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        copilot_state: dict[str, Any] | None = None,
        image_base64: str | None = None,
        image_mime_type: str | None = None,
        attached_document_name: str | None = None,
        agent_type: str = "summary",
    ) -> dict[str, Any]:
        from app.services.admin_copilot_service import (
            _build_agent_turn_response,
            _finalize_agent_reply,
            format_copilot_history,
        )
        from app.services.gpt.copilot_conversation_state import (
            merge_conversation_state,
            update_state_after_tools,
        )

        gpt = load_gpt_by_slug(db, SLUG_ADMIN)
        memory_lang = None
        if gpt:
            mem = load_gpt_memory(db, user_id=admin.id, gpt_id=gpt.id)
            if mem:
                facts = parse_facts(mem.facts_json)
                memory_lang = facts.get("preferred_response_language") or facts.get(
                    "preferred_language"
                )

        lang, lang_updated = resolve_language_for_turn(
            message,
            profile_language=admin.preferred_language,
            copilot_state=copilot_state,
            memory_language=memory_lang,
        )

        hist_text = format_copilot_history(conversation_history)
        state = merge_conversation_state(copilot_state, conversation_history)

        turn, graph_state = run_agent_graph(
            db,
            admin,
            message,
            language=lang,
            lang_updated=lang_updated,
            analysis_mode=analysis_mode,
            operational_context=operational_context,
            conversation_history=hist_text,
            copilot_state=copilot_state,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
            prefer_pro=len(message) > 200 or "critique" in message.lower(),
        )

        final_reply = _finalize_agent_reply(
            message,
            turn,
            db=db,
            admin=admin,
            agent_type=agent_type,
            context=operational_context or "",
            hist_text=hist_text,
            copilot_state=copilot_state,
        )

        session_state = merge_session_after_turn(
            copilot_state,
            language=lang,
            tools_used=turn.tools_used,
            intent=turn.intent or graph_state.intent,
            reply_summary=(final_reply or "")[:500],
        )
        state = update_state_after_tools(
            state,
            tools_used=turn.tools_used,
            tool_payloads=turn.tool_payloads or [],
            reply_summary=(final_reply or "")[:500],
        )
        merged_state = {**state.to_dict(), **session_state}

        # Sync mémoire unifiée ai_assistant
        from app.services.ai_assistant.conversation_state import ConversationState
        conv = ConversationState.from_copilot_state(merged_state)
        for tp in turn.tool_payloads or []:
            if tp.get("response", {}).get("status") != "error":
                conv.record_tool_success(tp.get("name", ""), tp.get("response") or {}, intent=turn.intent)
        merged_state = conv.merge_into_copilot_state(merged_state)

        response = _build_agent_turn_response(
            turn,
            task=message,
            agent_type=agent_type,
            reply=final_reply,
            copilot_state=merged_state,
        )

        response["language"] = lang
        response["mode"] = graph_state.mode
        response["confidence"] = graph_state.confidence
        response["reasoning_summary"] = graph_state.reasoning_summary
        response["execution_time_ms"] = round(graph_state.execution_ms, 1)
        response["sources_used"] = graph_state.rag_sources
        response["llm_provider"] = graph_state.mode
        response["llm_degraded"] = graph_state.mode not in {"jarvis", "ollama", "gemini", "gemini_pro"}

        return enrich_copilot_response(response)


def run_admin_ai_query(
    db: Session,
    admin: User,
    message: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return AdminAiService.run_turn(db, admin, message, **kwargs)
