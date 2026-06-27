"""Pipeline mémoire — intent → extraction → lookup → outil → réponse → mise à jour."""

from __future__ import annotations

from typing import Any

from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.entity_memory import EntityMemory
from app.services.ai_assistant.intent_router_v2 import IntentV2, classify_intent_v2
from app.services.ai_assistant.response_engine import format_tool_response, should_skip_llm_synthesis
from app.services.gpt.copilot_conversation_state import CopilotConversationState, update_state_after_tools


def build_memory_from_state(copilot_state: dict[str, Any] | None) -> EntityMemory:
    return EntityMemory.from_copilot_state(copilot_state)


def classify_turn(message: str, *, memory: EntityMemory | None = None) -> IntentV2:
    return classify_intent_v2(message, memory=memory)


def format_response_for_intent(
    intent: IntentV2,
    tool_name: str,
    payload: dict[str, Any],
    *,
    ui_language: str = "fr",
    message: str = "",
) -> str:
    return format_tool_response(intent, tool_name, payload, ui_language=ui_language, message=message)


def update_memory_after_tool(
    memory: EntityMemory,
    *,
    tool_name: str,
    payload: dict[str, Any],
    intent: IntentV2,
    reply: str | None = None,
) -> EntityMemory:
    memory.update_from_tool(
        tool_name,
        payload,
        intent=intent.specific_intent,
        query_type=intent.action.lower(),
        limit=intent.limit,
    )
    if reply:
        memory.last_result_summary = reply[:500]
    return memory


def attach_memory_to_response(
    response: dict[str, Any],
    *,
    memory: EntityMemory,
    copilot_state: dict[str, Any] | None,
    tools_used: list[str],
    tool_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    state = CopilotConversationState.from_dict(copilot_state)
    state = update_state_after_tools(
        state,
        tools_used=tools_used,
        tool_payloads=tool_payloads,
        reply_summary=(response.get("reply") or "")[:500],
    )
    conv = ConversationState.from_copilot_state(copilot_state)
    for p in tool_payloads:
        resp = p.get("response") or {}
        if isinstance(resp, dict):
            conv.enrich_from_tool(p.get("name") or "", resp, intent=response.get("intent"))
    conv.last_language = response.get("language") or conv.last_language
    state_dict = state.to_dict()
    state_dict.update(memory.to_state_updates())
    if intent_action := response.get("query_type"):
        state_dict["last_query_type"] = intent_action
    state_dict = conv.merge_into_copilot_state(state_dict)
    response["copilot_state"] = state_dict
    return response


def pipeline_should_use_direct_format(intent: IntentV2) -> bool:
    return should_skip_llm_synthesis(intent)
