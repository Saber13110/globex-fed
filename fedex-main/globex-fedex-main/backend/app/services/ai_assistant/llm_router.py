"""Routage LLM admin — Jarvis (Ollama llama3.2:3b) → synthèse locale."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.services.ai_assistant.timeout_utils import run_with_timeout
from app.services.gpt.model_gateway import generate_ollama_admin_fast
from app.services.gpt.tool_synthesis import synthesize_admin_tool_turn
from app.services.llm.providers import ollama_tool_agent_loop

logger = logging.getLogger(__name__)


@dataclass
class LlmSynthesisResult:
    reply: str
    mode: str
    tools_used: list[str]
    provider_detail: str | None = None


def _ollama_timeout_seconds() -> float:
    settings = get_settings()
    return float(
        getattr(settings, "ai_llm_ollama_timeout_seconds", None)
        or settings.ollama_timeout_seconds
        or 120.0
    )


def _local_synthesis(
    *,
    task: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str,
) -> LlmSynthesisResult | None:
    if not tool_payloads:
        return None
    fallback = synthesize_admin_tool_turn(
        task=task,
        tool_payloads=tool_payloads,
        ui_language=ui_language,
    )
    if fallback:
        return LlmSynthesisResult(
            reply=fallback,
            mode="local_fallback",
            tools_used=[p.get("name", "") for p in tool_payloads if p.get("name")],
        )
    return None


def _try_jarvis_tool_loop(
    *,
    system_instruction: str,
    user_payload: str,
    tool_declarations: list[dict[str, Any]],
    on_tool_call,
    max_rounds: int,
    max_output_tokens: int,
    timeout_seconds: float,
) -> LlmSynthesisResult | None:
    settings = get_settings()

    def _call() -> LlmSynthesisResult:
        logger.info("[LLM] provider selected: jarvis (%s)", settings.ollama_model)
        reply, tools_used = ollama_tool_agent_loop(
            system_instruction=system_instruction,
            user_payload=user_payload,
            tool_declarations=tool_declarations,
            on_tool_call=on_tool_call,
            max_rounds=max_rounds,
            max_output_tokens=max_output_tokens,
        )
        logger.info("[LLM] Jarvis/Ollama success")
        return LlmSynthesisResult(
            reply=reply or "",
            mode="jarvis",
            tools_used=list(tools_used or []),
            provider_detail=settings.ollama_model,
        )

    result = run_with_timeout(_call, timeout_seconds=timeout_seconds, label="jarvis-ollama")
    if result and (result.reply or result.tools_used):
        return result
    logger.warning("[LLM] Jarvis/Ollama error/timeout — fallback next")
    return None


def _try_jarvis_text_synthesis(
    *,
    task: str,
    user_payload: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str,
    timeout_seconds: float,
) -> LlmSynthesisResult | None:
    def _ollama_call() -> LlmSynthesisResult | None:
        logger.info("[LLM] provider selected: jarvis (text synthesis)")
        out = generate_ollama_admin_fast(
            task,
            context=user_payload[:4000],
            ui_language=ui_language,
            max_output_tokens=800,
        )
        if out.reply:
            logger.info("[LLM] Jarvis/Ollama text synthesis success")
            return LlmSynthesisResult(
                reply=out.reply,
                mode="jarvis",
                tools_used=[p.get("name", "") for p in tool_payloads if p.get("name")],
                provider_detail=get_settings().ollama_model,
            )
        return None

    return run_with_timeout(_ollama_call, timeout_seconds=timeout_seconds, label="jarvis-text")


def synthesize_with_router(
    *,
    task: str,
    system_instruction: str,
    user_payload: str,
    tool_declarations: list[dict[str, Any]],
    on_tool_call,
    tool_payloads: list[dict[str, Any]],
    ui_language: str,
    max_rounds: int = 2,
    max_output_tokens: int = 1024,
    prefer_pro: bool = False,
    tools_already_executed: bool = False,
) -> LlmSynthesisResult:
    del prefer_pro  # Gemini Pro retiré du cerveau admin
    ollama_timeout = _ollama_timeout_seconds()

    if not tools_already_executed and tool_declarations:
        jarvis_loop = _try_jarvis_tool_loop(
            system_instruction=system_instruction,
            user_payload=user_payload,
            tool_declarations=tool_declarations,
            on_tool_call=on_tool_call,
            max_rounds=max_rounds,
            max_output_tokens=max_output_tokens,
            timeout_seconds=ollama_timeout,
        )
        if jarvis_loop:
            return jarvis_loop

    if tool_payloads:
        jarvis_text = _try_jarvis_text_synthesis(
            task=task,
            user_payload=user_payload,
            tool_payloads=tool_payloads,
            ui_language=ui_language,
            timeout_seconds=ollama_timeout,
        )
        if jarvis_text:
            return jarvis_text

        local = _local_synthesis(task=task, tool_payloads=tool_payloads, ui_language=ui_language)
        if local:
            logger.info("[LLM] fallback used: local_fallback")
            return local

    local = _local_synthesis(task=task, tool_payloads=tool_payloads, ui_language=ui_language)
    if local:
        logger.info("[LLM] fallback used: local_fallback")
        return local

    from app.services.ai_assistant.deterministic_answer_engine import try_answer_from_tools_on_timeout

    det = try_answer_from_tools_on_timeout(task, tool_payloads, language=ui_language)
    if det:
        logger.info("[LLM] fallback used: deterministic_engine")
        return LlmSynthesisResult(
            reply=det,
            mode="deterministic",
            tools_used=[p.get("name", "") for p in tool_payloads if p.get("name")],
        )

    return LlmSynthesisResult(
        reply=(
            "Voici ce que je peux répondre avec les données disponibles. Reformulez votre question."
            if ui_language == "fr"
            else "Here is what I can answer from available data. Please rephrase."
        ),
        mode="local_fallback",
        tools_used=[p.get("name", "") for p in tool_payloads if p.get("name")],
    )
