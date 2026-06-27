"""Exécution outils entreprise avec résolution d'alias, timeout et métriques."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services.ai_assistant.health_metrics import record_tool_call
from app.services.ai_assistant.timeout_utils import run_with_timeout
from app.services.ai_assistant.tool_registry import default_args_for, resolve_handler
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext

logger = logging.getLogger(__name__)

_TOOL_TIMEOUT = 5.0


def build_tool_context(
    db: Session,
    user: User,
    *,
    analysis_mode: bool = True,
    ui_language: str = "fr",
    admin_direct_order: bool = False,
) -> ToolExecutionContext:
    role = (user.role or "admin").lower()
    return ToolExecutionContext(
        db=db,
        user_id=user.id,
        user_role=role,
        gpt_slug="fedex-admin-ops",
        actor_admin_id=user.id if role == "admin" else None,
        ui_language=ui_language,
        analysis_mode=analysis_mode,
        admin_direct_order=admin_direct_order,
    )


def _run_tool_inner(
    ctx: ToolExecutionContext,
    tool_name: str,
    merged: dict[str, Any],
) -> dict[str, Any]:
    from app.services.ai_assistant.composite_tools import run_composite_tool

    if tool_name in {
        "get_agent_missions_summary",
        "analyze_platform_health",
        "analyze_weekly_activity",
        "generate_security_report",
        "platform_health_report",
    }:
        return run_composite_tool(ctx, tool_name, merged)
    handler_name = resolve_handler(tool_name)
    result = execute_tool(ctx, ToolCall(name=handler_name, args=merged))
    return result.to_function_response()


def execute_enterprise_tool(
    ctx: ToolExecutionContext,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Exécute un outil avec timeout — ne bloque jamais l'assistant."""
    settings = get_settings()
    timeout = float(getattr(settings, "ai_tool_timeout_seconds", _TOOL_TIMEOUT) or _TOOL_TIMEOUT)
    if tool_name.startswith("export_"):
        timeout = max(timeout, 60.0)
    merged = {**default_args_for(tool_name), **(args or {})}
    start = time.perf_counter()
    logger.info("[AI] executing tool: %s", tool_name)

    def _call() -> dict[str, Any]:
        return _run_tool_inner(ctx, tool_name, merged)

    payload = run_with_timeout(_call, timeout_seconds=timeout, label=f"tool:{tool_name}")
    elapsed = (time.perf_counter() - start) * 1000

    if payload is None:
        logger.warning("[AI] tool timeout: %s", tool_name)
        record_tool_call(tool_name, success=False, latency_ms=elapsed)
        return {
            "name": tool_name,
            "handler": resolve_handler(tool_name),
            "response": {
                "status": "error",
                "error": f"Timeout outil {tool_name} ({timeout:.0f}s)",
            },
        }

    try:
        ok = payload.get("status") != "error" and "error" not in (payload or {})
        record_tool_call(tool_name, success=ok, latency_ms=elapsed)
        logger.info("[AI] tool finished: %s (%.0fms)", tool_name, elapsed)
        return {"name": tool_name, "handler": resolve_handler(tool_name), "response": payload}
    except Exception as exc:
        logger.warning("[AI] tool error: %s — %s", tool_name, exc)
        record_tool_call(tool_name, success=False, latency_ms=elapsed)
        return {
            "name": tool_name,
            "handler": resolve_handler(tool_name),
            "response": {"status": "error", "error": str(exc)[:300]},
        }


def safe_tool_call(
    ctx: ToolExecutionContext,
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    retries: int = 1,
) -> dict[str, Any]:
    """Exécute un outil avec retry, timeout et repli gracieux."""
    last_error = "erreur inconnue"
    for attempt in range(retries + 1):
        try:
            result = execute_enterprise_tool(ctx, tool_name, args)
            resp = result.get("response") or {}
            if resp.get("status") != "error":
                return result
            last_error = resp.get("error") or last_error
            logger.warning("[AI] safe_tool_call %s attempt %s failed: %s", tool_name, attempt + 1, last_error)
        except Exception as exc:
            last_error = str(exc)[:300]
            logger.warning("[AI] safe_tool_call %s attempt %s exception: %s", tool_name, attempt + 1, last_error)
    return {
        "name": tool_name,
        "handler": resolve_handler(tool_name),
        "response": {
            "status": "error",
            "error": f"Données partielles — {tool_name} indisponible ({last_error})",
        },
    }


def execute_tool_batch(
    ctx: ToolExecutionContext,
    planned: list[tuple[str, dict[str, Any]]],
    *,
    max_tools: int = 8,
) -> list[dict[str, Any]]:
    """Exécute les outils planifiés — continue même si un outil échoue."""
    results: list[dict[str, Any]] = []
    for name, args in planned[:max_tools]:
        results.append(safe_tool_call(ctx, name, args))
    return results
