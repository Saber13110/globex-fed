"""Budget Gemini par requête HTTP — limite d'appels et traçage."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)

_global_quota_until: float = 0.0

_gemini_ctx: ContextVar["GeminiRequestBudget | None"] = ContextVar(
    "gemini_request_budget",
    default=None,
)


def _cooldown_seconds() -> int:
    try:
        from app.core.config import get_settings

        return max(60, int(get_settings().gemini_quota_cooldown_seconds or 900))
    except Exception:
        return 900


def is_global_gemini_quota_exhausted() -> bool:
    """True si un 429 récent impose le repli Ollama/local (cooldown process-wide)."""
    return time.time() < _global_quota_until


def mark_global_gemini_quota_exhausted(*, cooldown_seconds: int | None = None) -> None:
    global _global_quota_until
    secs = max(60, int(cooldown_seconds or _cooldown_seconds()))
    _global_quota_until = time.time() + secs
    logger.warning(
        "Quota Gemini API saturé — cooldown %s s, repli Ollama/local jusqu'au reset.",
        secs,
    )


def reset_global_gemini_quota() -> None:
    """Tests / admin — annule le cooldown global."""
    global _global_quota_until
    _global_quota_until = 0.0


class GeminiBudgetError(Exception):
    """Quota ou budget Gemini épuisé pour la requête en cours."""


@dataclass
class GeminiRequestBudget:
    request_id: str
    max_calls: int = 2
    gemini_calls: int = 0
    models_used: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    fallback: str | None = None
    quota_exhausted: bool = False
    started_at: float = field(default_factory=time.perf_counter)

    def can_call_gemini(self) -> bool:
        if self.quota_exhausted:
            return False
        return self.gemini_calls < self.max_calls

    def record_call(self, model: str) -> None:
        self.gemini_calls += 1
        if model and model not in self.models_used:
            self.models_used.append(model)

    def mark_quota_exhausted(self) -> None:
        self.quota_exhausted = True

    def set_fallback(self, name: str) -> None:
        self.fallback = name

    def set_tools(self, tools: list[str]) -> None:
        self.tools_used = [t for t in tools if t]

    def log_summary(self) -> None:
        duration_ms = int((time.perf_counter() - self.started_at) * 1000)
        logger.info(
            "copilot_llm_trace request_id=%s gemini_calls=%s models=%s tools=%s "
            "fallback=%s duration_ms=%s quota_exhausted=%s",
            self.request_id,
            self.gemini_calls,
            ",".join(self.models_used) or "-",
            ",".join(self.tools_used) or "-",
            self.fallback or "-",
            duration_ms,
            self.quota_exhausted,
        )


class gemini_request_scope:
    """Contexte par requête copilot — limite et journalise les appels Gemini."""

    def __init__(
        self,
        *,
        request_id: str | None = None,
        max_calls: int = 2,
    ) -> None:
        self.request_id = (request_id or "").strip() or uuid.uuid4().hex[:12]
        self.max_calls = max(1, max_calls)
        self._token: ContextVar.Token | None = None
        self.budget: GeminiRequestBudget | None = None

    def __enter__(self) -> GeminiRequestBudget:
        self.budget = GeminiRequestBudget(
            request_id=self.request_id,
            max_calls=self.max_calls,
        )
        self._token = _gemini_ctx.set(self.budget)
        return self.budget

    def __exit__(self, *args: object) -> None:
        if self.budget is not None:
            self.budget.log_summary()
        if self._token is not None:
            _gemini_ctx.reset(self._token)


def get_gemini_budget() -> GeminiRequestBudget | None:
    return _gemini_ctx.get()


def should_skip_gemini() -> bool:
    if is_global_gemini_quota_exhausted():
        return True
    ctx = get_gemini_budget()
    if ctx is None:
        return False
    return ctx.quota_exhausted or not ctx.can_call_gemini()


def mark_gemini_quota_exhausted() -> None:
    ctx = get_gemini_budget()
    if ctx is not None:
        ctx.mark_quota_exhausted()
    mark_global_gemini_quota_exhausted()


def reserve_gemini_call(model: str) -> None:
    """Réserve un appel Gemini ; lève GeminiBudgetError si interdit."""
    ctx = get_gemini_budget()
    if ctx is None:
        return
    if ctx.quota_exhausted:
        raise GeminiBudgetError("Quota Gemini épuisé (429) — pas de nouvel appel dans ce cycle.")
    if not ctx.can_call_gemini():
        raise GeminiBudgetError(
            f"Budget Gemini atteint ({ctx.gemini_calls}/{ctx.max_calls}) pour request_id={ctx.request_id}."
        )
    ctx.record_call(model)


def note_fallback(provider: str) -> None:
    ctx = get_gemini_budget()
    if ctx is not None:
        ctx.set_fallback(provider)


def note_tools(tools: list[str]) -> None:
    ctx = get_gemini_budget()
    if ctx is not None:
        ctx.set_tools(tools)
