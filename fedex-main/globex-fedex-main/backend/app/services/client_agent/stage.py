# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Drapeau CLIENT_AGENT_STAGE — activation incrémentale des capacités."""
#
# from __future__ import annotations
#
# from app.core.config import get_settings
#
# # Jalons alignés sur le plan refonte incrémentale
# STAGE_PLANNER = 1
# STAGE_CONTEXT = 2
# STAGE_FEDEX = 3
# STAGE_RENDERERS = 4
# STAGE_FAQ = 5
# STAGE_GUARD = 6
# STAGE_AUTOMATION = 7
# STAGE_POD_MAP = 8
# STAGE_OLLAMA = 9
# STAGE_TOOL_LOOP = 10
# STAGE_GOLDEN = 11
# STAGE_PROD = 12
#
#
# def current_stage() -> int:
#     raw = getattr(get_settings(), "client_agent_stage", STAGE_PROD)
#     try:
#         stage = int(raw)
#     except (TypeError, ValueError):
#         stage = STAGE_PROD
#     return max(STAGE_PLANNER, min(STAGE_PROD, stage))
#
#
# def stage_at_least(minimum: int) -> bool:
#     return current_stage() >= minimum
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
