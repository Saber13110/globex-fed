"""Exécution sécurisée des outils — timeout 5s, retour standardisé, pas de crash."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.tool_executor import build_tool_context, safe_tool_call

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_S = 5.0
GLOBAL_DEADLINE_S = 15.0


def execute_tool_plan(
    db: Session,
    admin: User,
    plan: list[tuple[str, dict[str, Any]]],
    *,
    deadline: float | None = None,
    ui_language: str = "fr",
) -> list[dict[str, Any]]:
    """Exécute un plan d'outils — continue même si un outil échoue."""
    if deadline is None:
        deadline = time.monotonic() + GLOBAL_DEADLINE_S
    ctx = build_tool_context(db, admin, ui_language=ui_language)
    results: list[dict[str, Any]] = []
    for tool_name, args in plan:
        if time.monotonic() > deadline:
            logger.warning("[SafeExecutor] deadline reached before %s", tool_name)
            break
        try:
            item = safe_tool_call(ctx, tool_name, args)
            payload = item.get("response") or {}
            results.append({
                "name": tool_name,
                "response": payload,
                "ok": payload.get("status") != "error",
            })
        except Exception as exc:
            logger.warning("[SafeExecutor] tool %s failed: %s", tool_name, exc)
            results.append({
                "name": tool_name,
                "response": {"status": "error", "message": str(exc)[:200]},
                "ok": False,
            })
    return results
