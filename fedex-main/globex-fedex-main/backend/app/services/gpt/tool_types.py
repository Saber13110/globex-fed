"""Types pour le registre d'outils GPT (Phase 2 — function calling Gemini)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    allowed_roles: frozenset[str]
    sensitivity: str = "read"  # read | write | destructive
    requires_approval: bool = False
    gpt_slugs: frozenset[str] = frozenset({"fedex-admin-ops", "fedex-client"})

    def to_gemini_declaration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description[:512],
            "parameters": self.parameters,
        }

    @property
    def is_read_tool(self) -> bool:
        return self.sensitivity == "read" and not self.requires_approval

    @property
    def is_action_tool(self) -> bool:
        return not self.is_read_tool


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    needs_approval: bool = False
    approval_hint: str | None = None

    def to_function_response(self) -> dict[str, Any]:
        if self.needs_approval:
            return {
                "status": "approval_required",
                "message": self.approval_hint or "Action sensible — approbation admin requise.",
                **self.data,
            }
        if not self.success:
            out: dict[str, Any] = {"status": "error", "error": self.error or "Échec outil"}
            if self.data:
                out.update(self.data)
            return out
        return {"status": "ok", **self.data}


ToolHandler = Callable[..., ToolResult]


@dataclass
class ToolExecutionContext:
    db: Session
    user_id: int
    user_role: str
    gpt_slug: str
    actor_admin_id: int | None = None
    ui_language: str = "fr"
    analysis_mode: bool = False
    admin_direct_order: bool = False
    skip_approval: bool = False
    session_id: int | None = None
