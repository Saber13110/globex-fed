# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Capacités progressives de l'assistant client (Phase 1 → 4)."""
#
# from __future__ import annotations
#
# from app.core.config import get_settings
#
# CAP_CHAT = "chat"
# CAP_FEDEX = "fedex"
# CAP_PDF = "pdf"
# CAP_EXCEL = "excel"
#
# _ALL_CAPS = frozenset({CAP_CHAT, CAP_FEDEX, CAP_PDF, CAP_EXCEL})
#
#
# def parse_capabilities(raw: str | None) -> frozenset[str]:
#     if not raw or not str(raw).strip():
#         return frozenset({CAP_CHAT})
#     parts = {p.strip().lower() for p in str(raw).split(",") if p.strip()}
#     return frozenset(parts & _ALL_CAPS) or frozenset({CAP_CHAT})
#
#
# def client_capabilities() -> frozenset[str]:
#     return parse_capabilities(get_settings().client_agent_capabilities)
#
#
# def has_client_capability(cap: str) -> bool:
#     return cap.lower() in client_capabilities()
#
#
# def is_phase1_chat_only() -> bool:
#     """Phase 1 : chat seul, sans FedEx ni exports."""
#     caps = client_capabilities()
#     return CAP_CHAT in caps and CAP_FEDEX not in caps
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
