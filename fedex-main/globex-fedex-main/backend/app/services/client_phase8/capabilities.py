"""Capacités Phase 8 — rapport d'activité quotidien."""

from __future__ import annotations

from app.core.config import get_settings

CAP_DAILY_REPORT = "daily_report"


def _parsed_caps() -> frozenset[str]:
    raw = get_settings().client_agent_capabilities or ""
    if not raw.strip():
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def router_enabled() -> bool:
    return bool(get_settings().client_agent_router_enabled)


def has_daily_report_capability() -> bool:
    return CAP_DAILY_REPORT in _parsed_caps()
