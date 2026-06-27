"""Globex OS Agent — remplace le copilot admin."""

from __future__ import annotations

from typing import Any

__all__ = [
    "run_globex_agent_chat",
    "execute_globex_tool",
    "check_globex_agent_health",
    "list_globex_agent_tools",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from app.services.globex_agent import kernel as _kernel

        return getattr(_kernel, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
