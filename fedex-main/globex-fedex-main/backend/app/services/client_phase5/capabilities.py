"""Capacités Phase 5 — notifications client."""

from __future__ import annotations

from app.core.config import get_settings

CAP_NOTIFICATIONS = "notifications"


def _parsed_caps() -> frozenset[str]:
    raw = get_settings().client_agent_capabilities or ""
    if not raw.strip():
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def router_enabled() -> bool:
    return bool(get_settings().client_agent_router_enabled)


def has_notifications_capability() -> bool:
    return CAP_NOTIFICATIONS in _parsed_caps()
