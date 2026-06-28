"""Capacités Phase 9 — lecture documents."""

from __future__ import annotations

from app.core.config import get_settings

CAP_DOCUMENT_READ = "document_read"


def _parsed_caps() -> frozenset[str]:
    raw = get_settings().client_agent_capabilities or ""
    if not raw.strip():
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def has_document_read_capability() -> bool:
    return CAP_DOCUMENT_READ in _parsed_caps()
