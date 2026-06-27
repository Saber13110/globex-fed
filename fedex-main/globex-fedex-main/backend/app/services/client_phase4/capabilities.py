"""Capacités Phase 4 — indépendant de client_phase3 (pdf/excel)."""

from __future__ import annotations

from app.core.config import get_settings

CAP_SESSIONS = "sessions"


def _parsed_caps() -> frozenset[str]:
    raw = get_settings().client_agent_capabilities or ""
    if not raw.strip():
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def router_enabled() -> bool:
    return bool(get_settings().client_agent_router_enabled)


def has_sessions_capability() -> bool:
    return CAP_SESSIONS in _parsed_caps()
