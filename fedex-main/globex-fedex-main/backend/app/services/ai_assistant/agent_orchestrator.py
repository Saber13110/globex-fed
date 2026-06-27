"""
Orchestrateur agent entreprise — graphe multi-étapes (LangGraph-compatible).

Pipeline :
  resolve_language → classify_intent → plan_tools → execute_tools → rag → llm → validate
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services.ai_assistant.conversation_manager import build_reasoning_summary
from app.services.ai_assistant.health_metrics import record_request
from app.services.ai_assistant.language_service import language_label
from app.services.ai_assistant.llm_router import synthesize_with_router
from app.services.ai_assistant.memory_service import (
    build_agent_memory_block,
    persist_language_preference,
)
from app.services.ai_assistant.rag_service import search_knowledge
from app.services.ai_assistant.response_validator import validate_response
from app.services.ai_assistant.tool_executor import (
    build_tool_context,
    execute_tool_batch,
)
from app.services.ai_assistant.timeout_utils import Deadline
from app.services.ai_assistant.tool_planner import plan_tools
from app.services.gpt.admin_reasoning_engine import (
    build_admin_reasoning_prompt,
    filter_tools_for_admin_mode,
)
from app.services.gpt.agent_runtime import AGENT_TOOLS_SYSTEM_APPEND, GptAgentTurnResult
from app.services.gpt.orchestrator import SLUG_ADMIN, _classify_intent, load_gpt_by_slug
from app.services.gpt.prompt_composer import build_gpt_user_payload
from app.services.gpt.prompts import admin_gpt_system_for_lang
from app.services.gpt.tool_registry import gemini_tool_declarations, list_tools_for_gpt
from app.services.gpt.tool_types import ToolCall
from app.services.gpt.tool_executor import execute_tool

logger = logging.getLogger(__name__)

_ENTERPRISE_SYSTEM = """
Tu es **Jarvis**, assistant IA admin de la plateforme Globex FedEx (niveau entreprise).
Moteur local : Ollama (llama3.2:3b).

RÈGLES ABSOLUES :
- Ne jamais inventer de chiffres, utilisateurs, tickets, notifications, trackings ou logs.
- Toute donnée factuelle provient des OUTILS BACKEND ou du RAG — cite implicitement la source.
- Si une donnée manque : « Je n'ai pas accès à cette donnée actuellement » + précise l'outil/table.
- Réponds dans la langue active ({language_label}) — ton professionnel, clair, structuré.
- Structure : titres courts, points clés, actions recommandées si pertinent.
- Pour les synthèses multi-outils : croise logs, sécurité, notifications, tickets et tracking.
"""


@dataclass
class AgentGraphState:
    message: str
    language: str = "fr"
    intent: str = "general_question"
    planned_tools: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    agent_steps: list[dict[str, Any]] = field(default_factory=list)
    rag_sources: list[dict[str, Any]] = field(default_factory=list)
    rag_block: str = ""
    reply: str = ""
    mode: str = "jarvis"
    confidence: float = 0.85
    reasoning_summary: str = ""
    validation_warning: str | None = None
    side_effects: dict[str, Any] = field(default_factory=dict)
    execution_ms: float = 0.0
    prefer_pro: bool = False


GraphNode = Callable[["AgentOrchestrator", AgentGraphState], AgentGraphState]


class AgentOrchestrator:
    """Graphe d'orchestration agent — exécute les nœuds séquentiellement."""

    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user
        self.settings = get_settings()
        self.gpt = load_gpt_by_slug(db, SLUG_ADMIN)
        if self.gpt is None:
            raise ValueError("GPT admin introuvable")

    @property
    def nodes(self) -> list[tuple[str, GraphNode]]:
        return [
            ("resolve_language", self._node_resolve_language),
            ("classify_intent", self._node_classify_intent),
            ("plan_tools", self._node_plan_tools),
            ("execute_tools", self._node_execute_tools),
            ("rag_retrieve", self._node_rag),
            ("llm_synthesize", self._node_llm),
            ("validate", self._node_validate),
        ]

    def run(
        self,
        state: AgentGraphState,
        *,
        analysis_mode: bool = True,
        operational_context: str | None = None,
        conversation_history: str | None = None,
        copilot_state: dict[str, Any] | None = None,
        image_base64: str | None = None,
        image_mime_type: str | None = None,
        attached_document_name: str | None = None,
        lang_updated: bool = False,
    ) -> GptAgentTurnResult:
        t0 = time.perf_counter()
        deadline = Deadline(float(self.settings.ai_timeout_seconds or 30.0))
        state.side_effects["_ctx"] = {
            "analysis_mode": analysis_mode,
            "operational_context": operational_context or "",
            "conversation_history": conversation_history or "",
            "copilot_state": copilot_state,
            "image_base64": image_base64,
            "image_mime_type": image_mime_type,
            "attached_document_name": attached_document_name,
            "lang_updated": lang_updated,
            "deadline": deadline,
        }

        for name, node in self.nodes:
            if deadline.expired():
                logger.warning("[AI] timeout — skipping node %s", name)
                break
            try:
                state = node(state)
            except Exception as exc:
                logger.warning("[AI] error — node %s: %s", name, exc)
                state.agent_steps.append({"label": name, "status": "error", "detail": str(exc)[:200]})

        if not (state.reply or "").strip() and deadline.expired():
            from app.services.ai_assistant.deterministic_answer_engine import try_answer_from_tools_on_timeout

            local = try_answer_from_tools_on_timeout(
                state.message,
                state.tool_payloads,
                language=state.language,
            )
            if not local and state.tool_payloads:
                from app.services.gpt.tool_synthesis import synthesize_admin_tool_turn
                local = synthesize_admin_tool_turn(
                    task=state.message,
                    tool_payloads=state.tool_payloads,
                    ui_language=state.language,
                )
            state.reply = local or (
                "Voici les données disponibles à partir des outils consultés. "
                "Reformulez si vous souhaitez plus de détails."
            )
            state.mode = "deterministic" if local else "timeout_fallback"
            state.confidence = 0.82 if local else 0.5
            state.reasoning_summary = "Réponse déterministe (timeout Gemini)." if local else "Timeout global atteint."
            logger.error("[AI] timeout — fallback deterministic=%s", bool(local))

        state.execution_ms = (time.perf_counter() - t0) * 1000
        record_request(
            mode=state.mode,
            success=bool(state.reply),
            latency_ms=state.execution_ms,
            error=state.validation_warning,
        )

        sources = [
            s.get("title") or str(s.get("chunk_id", ""))
            for s in state.rag_sources
            if isinstance(s, dict)
        ]
        return GptAgentTurnResult(
            reply=state.reply,
            intent=state.intent,
            llm_provider=state.mode,
            gpt_slug=SLUG_ADMIN,
            knowledge_sources=sources,
            tools_used=state.tools_used,
            tool_payloads=state.tool_payloads,
            agent_steps=state.agent_steps,
            action_executed=state.side_effects.get("action_executed", False),
            needs_approval=state.side_effects.get("needs_approval", False),
            export_download=state.side_effects.get("export_download"),
        )

    def _node_resolve_language(self, state: AgentGraphState) -> AgentGraphState:
        ctx = state.side_effects["_ctx"]
        if ctx.get("lang_updated"):
            persist_language_preference(
                self.db, user=self.user, gpt=self.gpt, language=state.language,
            )
        state.agent_steps.append({
            "label": "language",
            "status": "done",
            "detail": state.language,
        })
        return state

    def _node_classify_intent(self, state: AgentGraphState) -> AgentGraphState:
        state.intent = _classify_intent(state.message, SLUG_ADMIN)
        logger.info("[AI] intent detected: %s", state.intent)
        state.agent_steps.append({
            "label": "intent",
            "status": "done",
            "detail": state.intent,
        })
        return state

    def _node_plan_tools(self, state: AgentGraphState) -> AgentGraphState:
        ctx = state.side_effects.get("_ctx") or {}
        copilot_state = ctx.get("copilot_state")
        from app.services.ai_assistant.entity_memory import (
            EntityMemory,
            resolve_message_with_entities,
        )
        memory = EntityMemory.from_copilot_state(copilot_state)
        resolved, _ = resolve_message_with_entities(state.message, memory)
        if resolved != state.message:
            state.message = resolved
        state.planned_tools = plan_tools(resolved, state.intent, copilot_state=copilot_state)
        if state.planned_tools:
            names = [t[0] for t in state.planned_tools]
            logger.info("[AI] selected tools: %s", names)
            state.agent_steps.append({
                "label": "plan",
                "status": "done",
                "detail": ", ".join(names[:8]),
            })
        return state

    def _node_execute_tools(self, state: AgentGraphState) -> AgentGraphState:
        if not state.planned_tools:
            return state
        ctx = state.side_effects["_ctx"]
        tool_ctx = build_tool_context(
            self.db,
            self.user,
            analysis_mode=ctx.get("analysis_mode", True),
            ui_language=state.language,
        )
        results = execute_tool_batch(tool_ctx, state.planned_tools)
        for item in results:
            name = item["name"]
            payload = item["response"]
            state.tool_payloads.append({"name": name, "response": payload})
            state.tools_used.append(name)
            status = "done" if payload.get("status") != "error" else "error"
            state.agent_steps.append({"label": name, "status": status, "detail": None})
            resp = payload
            if resp.get("needs_approval"):
                state.side_effects["needs_approval"] = True
            if resp.get("export_download"):
                state.side_effects["export_download"] = resp["export_download"]
                state.side_effects["action_executed"] = True
        return state

    def _node_rag(self, state: AgentGraphState) -> AgentGraphState:
        ctx = state.side_effects["_ctx"]
        deadline: Deadline | None = ctx.get("deadline")
        if deadline and deadline.expired():
            return state
        if state.tool_payloads and deadline and deadline.remaining() < 8:
            return state
        rag = search_knowledge(
            self.db,
            gpt=self.gpt,
            query=state.message,
            language=state.language,
            top_k=5 if ctx.get("attached_document_name") else 3,
        )
        state.rag_sources = rag["sources"]
        state.rag_block = rag["block"]
        if rag["count"]:
            state.agent_steps.append({
                "label": "rag",
                "status": "done",
                "detail": f"{rag['count']} source(s)",
            })
        return state

    def _node_llm(self, state: AgentGraphState) -> AgentGraphState:
        ctx = state.side_effects["_ctx"]
        lang_label = language_label(state.language)
        system = admin_gpt_system_for_lang(state.language)
        system += "\n\n" + _ENTERPRISE_SYSTEM.format(language_label=lang_label)
        system += f"\n\n{AGENT_TOOLS_SYSTEM_APPEND}\n\n"
        system += build_admin_reasoning_prompt(
            analysis_mode=ctx.get("analysis_mode", True),
            lang=state.language,
        )

        memory_block = build_agent_memory_block(
            self.db,
            gpt=self.gpt,
            user=self.user,
            session_id=None,
            copilot_state=ctx.get("copilot_state"),
        )
        from app.services.ai_assistant.entity_memory import (
            EntityMemory,
            build_entity_context_block,
            resolve_message_with_entities,
        )
        entity_mem = EntityMemory.from_copilot_state(ctx.get("copilot_state"))
        resolved_msg, _ = resolve_message_with_entities(state.message, entity_mem)
        entity_block = build_entity_context_block(entity_mem)
        if entity_block:
            memory_block = f"{memory_block}\n\n{entity_block}".strip()
        if resolved_msg != state.message:
            state.message = resolved_msg

        tool_data_block = ""
        if state.tool_payloads:
            tool_data_block = "DONNÉES OUTILS (source fiable — ne pas inventer):\n"
            tool_data_block += json.dumps(
                state.tool_payloads, ensure_ascii=False, default=str,
            )[:12000]

        payload = build_gpt_user_payload(
            state.message,
            knowledge_text=state.rag_block,
            memory_text=memory_block,
            operational_context=(
                f"{ctx.get('operational_context', '')}\n\n{tool_data_block}".strip()
            ),
            ui_language=state.language,
            conversation_history=ctx.get("conversation_history"),
        )

        role = (self.user.role or "admin").lower()
        tools = filter_tools_for_admin_mode(
            list_tools_for_gpt(self.gpt, user_role=role),
            analysis_mode=ctx.get("analysis_mode", True),
        )
        declarations = gemini_tool_declarations(tools)
        tool_ctx = build_tool_context(
            self.db,
            self.user,
            analysis_mode=ctx.get("analysis_mode", True),
            ui_language=state.language,
        )
        llm_tools_used: list[str] = list(state.tools_used)
        llm_payloads: list[dict[str, Any]] = list(state.tool_payloads)

        def _on_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
            state.agent_steps.append({
                "label": name, "status": "running",
                "detail": json.dumps(args, ensure_ascii=False)[:150],
            })
            result = execute_tool(tool_ctx, ToolCall(name=name, args=args))
            resp = result.to_function_response()
            llm_payloads.append({"name": name, "response": resp})
            if name not in llm_tools_used:
                llm_tools_used.append(name)
            if result.needs_approval:
                state.side_effects["needs_approval"] = True
            if result.data.get("export_download"):
                state.side_effects["export_download"] = result.data["export_download"]
                state.side_effects["action_executed"] = True
            state.agent_steps.append({
                "label": name,
                "status": "done" if result.success else "error",
                "detail": result.error,
            })
            return resp

        result = synthesize_with_router(
            task=state.message,
            system_instruction=system,
            user_payload=payload,
            tool_declarations=declarations,
            on_tool_call=_on_tool,
            tool_payloads=llm_payloads,
            ui_language=state.language,
            max_rounds=2,
            prefer_pro=state.prefer_pro or bool(ctx.get("prefer_pro")),
            tools_already_executed=bool(state.tool_payloads),
        )

        if state.tool_payloads and result.mode == "local_fallback":
            from app.services.ai_assistant.reasoning_engine import synthesize_enterprise_response
            from app.services.ai_assistant.entity_memory import build_entity_context_block, EntityMemory

            entity_ctx = build_entity_context_block(
                EntityMemory.from_copilot_state(ctx.get("copilot_state")),
            )
            enterprise = synthesize_enterprise_response(
                state.message,
                llm_payloads,
                lang=state.language,
                entity_context=entity_ctx,
                prefer_pro=state.prefer_pro,
            )
            state.reply = enterprise.reply
            state.mode = enterprise.mode
            state.confidence = enterprise.confidence
        else:
            state.reply = result.reply
            state.mode = result.mode
        logger.info("[AI] provider response received: %s", state.mode)
        for t in result.tools_used:
            if t and t not in state.tools_used:
                state.tools_used.append(t)
        state.tool_payloads = llm_payloads
        return state

    def _node_validate(self, state: AgentGraphState) -> AgentGraphState:
        from app.services.ai_assistant.response_sanitizer import sanitize_reply

        reply, confidence, warning = validate_response(
            message=state.message,
            reply=state.reply,
            tools_used=state.tools_used,
            tool_payloads=state.tool_payloads,
        )
        reply = sanitize_reply(reply, tool_payloads=state.tool_payloads)
        state.reply = reply
        state.confidence = confidence
        state.validation_warning = warning
        state.reasoning_summary = build_reasoning_summary(
            message=state.message[:120],
            intent=state.intent,
            planned_tools=[t[0] for t in state.planned_tools],
            tools_used=state.tools_used,
            mode=state.mode,
        )
        state.agent_steps.append({
            "label": "validate",
            "status": "done" if not warning else "warning",
            "detail": warning,
        })
        return state


def run_agent_graph(
    db: Session,
    user: User,
    message: str,
    *,
    language: str,
    lang_updated: bool = False,
    analysis_mode: bool = True,
    operational_context: str | None = None,
    conversation_history: str | None = None,
    copilot_state: dict[str, Any] | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    attached_document_name: str | None = None,
    prefer_pro: bool = False,
) -> tuple[GptAgentTurnResult, AgentGraphState]:
    orchestrator = AgentOrchestrator(db, user)
    state = AgentGraphState(message=message, language=language, prefer_pro=prefer_pro)
    turn = orchestrator.run(
        state,
        analysis_mode=analysis_mode,
        operational_context=operational_context,
        conversation_history=conversation_history,
        copilot_state=copilot_state,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
        attached_document_name=attached_document_name,
        lang_updated=lang_updated,
    )
    return turn, state
