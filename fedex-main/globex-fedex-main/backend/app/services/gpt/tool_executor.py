"""Exécution des outils GPT — permissions, politique d'approbation, dispatch handlers."""

from __future__ import annotations

import logging
from typing import Any

from app.services.globex_agent.approval_policy import (
    approval_hint_for,
    should_require_approval,
)
from app.services.gpt.admin_reasoning_engine import action_requires_agent_mode_message
from app.services.gpt.tool_handlers import HANDLERS
from app.services.gpt.tool_registry import get_tool
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


def execute_tool(ctx: ToolExecutionContext, call: ToolCall) -> ToolResult:
    """Exécute un outil si autorisé ; sinon erreur ou demande d'approbation."""
    definition = get_tool(call.name)
    if definition is None:
        return ToolResult(name=call.name, success=False, error=f"Outil inconnu : {call.name}")

    role = (ctx.user_role or "client").lower()
    if role not in definition.allowed_roles and role != "admin":
        return ToolResult(
            name=call.name,
            success=False,
            error=f"Permission refusée pour le rôle {role}.",
        )

    if ctx.gpt_slug not in definition.gpt_slugs and definition.gpt_slugs:
        return ToolResult(
            name=call.name,
            success=False,
            error=f"Outil non disponible pour le GPT {ctx.gpt_slug}.",
        )

    if ctx.analysis_mode and definition.is_action_tool:
        lang = (ctx.ui_language or "fr").lower()[:2]
        if lang not in {"fr", "en", "ar"}:
            lang = "fr"
        return ToolResult(
            name=call.name,
            success=False,
            error=action_requires_agent_mode_message(lang),
            data={"requires_agent_mode": True},
        )

    args = dict(call.args or {})
    if ctx.skip_approval:
        args["_skip_approval"] = True

    needs_approval = (
        not ctx.skip_approval
        and should_require_approval(
            call.name,
            admin_direct_order=ctx.admin_direct_order,
            agent_initiated=not ctx.admin_direct_order,
        )
    )

    if needs_approval:
        return ToolResult(
            name=call.name,
            success=True,
            needs_approval=True,
            approval_hint=approval_hint_for(call.name, args),
            data={"parameters": args, "tool": call.name},
        )

    handler = HANDLERS.get(call.name)
    if handler is None:
        return ToolResult(name=call.name, success=False, error="Handler non implémenté.")

    try:
        return handler(ctx, args)
    except Exception as exc:
        logger.exception("Échec outil %s", call.name)
        return ToolResult(name=call.name, success=False, error=str(exc)[:400])
