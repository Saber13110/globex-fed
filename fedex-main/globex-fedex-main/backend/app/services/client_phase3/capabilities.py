"""Capacités progressives assistant client (Phase 3)."""

from __future__ import annotations

from app.core.config import get_settings

CAP_CHAT = "chat"
CAP_FEDEX = "fedex"
CAP_PDF = "pdf"
CAP_EXCEL = "excel"

_ALL_CAPS = frozenset({CAP_CHAT, CAP_FEDEX, CAP_PDF, CAP_EXCEL})


def parse_capabilities(raw: str | None) -> frozenset[str]:
    if not raw or not str(raw).strip():
        return frozenset({CAP_CHAT})
    parts = {p.strip().lower() for p in str(raw).split(",") if p.strip()}
    return frozenset(parts & _ALL_CAPS) or frozenset({CAP_CHAT})


def client_capabilities() -> frozenset[str]:
    return parse_capabilities(get_settings().client_agent_capabilities)


def has_capability(cap: str) -> bool:
    return cap.lower() in client_capabilities()
