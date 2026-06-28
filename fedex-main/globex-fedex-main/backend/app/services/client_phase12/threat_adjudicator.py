"""Arbitre Ollama — zone grise sécurité."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.client_phase12.router_prompt import SECURITY_ADJUDICATOR_PROMPT
from app.services.llm.providers import LlmProviderError, call_ollama_agent_plan
from app.services.prompt_guard_service import RiskLevel, RiskResult

logger = logging.getLogger(__name__)


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


def adjudicate_gray_zone(
    text: str,
    heuristic: RiskResult,
    *,
    ui_language: str | None,
) -> RiskResult:
    try:
        raw = call_ollama_agent_plan(
            text,
            system_prompt=SECURITY_ADJUDICATOR_PROMPT,
            conversation_history="",
            session_titles="",
            ui_language=ui_language,
        )
    except LlmProviderError:
        logger.warning("Phase 12 adjudicator Ollama unavailable", exc_info=True)
        return heuristic

    data = _parse_json_object(raw)
    if not data:
        return heuristic

    action = str(data.get("action") or "").strip().lower()
    verdict = str(data.get("verdict") or "").strip().lower()
    biz = str(data.get("business_intent") or "other").strip().lower()

    if action == "block" or verdict == "attack":
        reasons = list(heuristic.reasons) + ["ollama_adjudicator:attack"]
        return RiskResult(score=max(heuristic.score, 85), level=RiskLevel.block, reasons=reasons)

    if action == "allow" or verdict == "benign" or biz not in ("", "other"):
        reasons = [f"business_intent:{biz}"] if biz not in ("", "other") else ["ollama_adjudicator:benign"]
        return RiskResult(score=0, level=RiskLevel.ok, reasons=reasons)

    if action == "warn" or verdict == "suspicious":
        reasons = list(heuristic.reasons) + ["ollama_adjudicator:suspicious"]
        return RiskResult(score=heuristic.score, level=RiskLevel.warn, reasons=reasons)

    return heuristic
