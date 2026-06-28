"""Capacités Phase 12 — smart guard sécurité."""

from __future__ import annotations

from app.core.config import get_settings

CAP_SECURITY_SMART_GUARD = "security_smart_guard"


def _parsed_caps() -> frozenset[str]:
    raw = get_settings().client_agent_capabilities or ""
    if not raw.strip():
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def has_security_smart_guard_capability() -> bool:
    return CAP_SECURITY_SMART_GUARD in _parsed_caps()


def smart_guard_enabled() -> bool:
    settings = get_settings()
    return bool(
        settings.prompt_guard_enabled
        and settings.security_smart_guard_enabled
        and has_security_smart_guard_capability()
    )
