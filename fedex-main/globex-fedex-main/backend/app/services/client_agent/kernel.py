# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Noyau client — entrée LLM unique via tool_bridge (orchestrateur Ollama + outils)."""
#
# from __future__ import annotations
#
# import logging
# from typing import Any
#
# from sqlalchemy.orm import Session
#
# from app.core.config import get_settings
# from app.models.chat_session import ChatSession
# from app.models.user import User
# from app.services.chat_session_context import (
#     build_conversation_history_for_llm,
#     resolve_tracking_for_message,
# )
# from app.services.client_agent.capabilities import is_phase1_chat_only
# from app.services.client_agent.export_turn import handle_export_turn
# from app.services.client_agent.ollama_bridge import chat_turn
# from app.services.client_agent.history import load_ollama_history
# from app.services.client_agent.tool_bridge import (
#     _prefetch_fedex_context,
#     finalize_client_tracking_turn,
#     run_client_tool_turn,
# )
# from app.services.client_agent.types import ClientTurnResult
# from app.services.client_reply_safety import fedex_deterministic_reply_if_available
# from app.services.llm.providers import resolve_ui_language
#
# logger = logging.getLogger(__name__)
#
# _FALLBACK_REPLY = (
#     "Désolé, une erreur technique est survenue. "
#     "Réessayez dans un instant ou vérifiez qu'Ollama est lancé."
# )
#
#
# def run_turn(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     **kwargs: Any,
# ) -> ClientTurnResult:
#     """Traite un tour client : LLM + outils en entrée unique ; repli si LLM désactivé."""
#     settings = get_settings()
#     ui_language = kwargs.get("ui_language")
#     probe = (message or "").strip()
#     exclude_id = kwargs.get("current_user_message_id")
#     has_image = bool((kwargs.get("image_base64") or "").strip())
#
#     history_text = build_conversation_history_for_llm(
#         db,
#         session_id=session.id,
#         exclude_message_id=exclude_id,
#     )
#
#     tracking, tracking_source = resolve_tracking_for_message(
#         db,
#         session_id=session.id,
#         user_id=user.id,
#         message=probe,
#         conversation_history=history_text,
#     )
#
#     phase1 = is_phase1_chat_only()
#     use_tool_bridge = (
#         settings.llm_enabled
#         and settings.gpt_tools_enabled
#         and (settings.client_tool_loop_enabled or phase1)
#     )
#
#     if use_tool_bridge:
#         return run_client_tool_turn(
#             db,
#             user,
#             probe,
#             session,
#             ui_language=ui_language,
#             preferred_name=kwargs.get("preferred_name"),
#             response_preferences=kwargs.get("response_preferences"),
#             image_base64=kwargs.get("image_base64"),
#             image_mime_type=kwargs.get("image_mime_type"),
#             current_user_message_id=exclude_id,
#             resolved_tracking=tracking,
#             tracking_source=tracking_source,
#         )
#
#     if phase1:
#         return ClientTurnResult(
#             reply=_FALLBACK_REPLY,
#             source="fallback",
#             intent="client_agent",
#             agent_mode=True,
#         )
#
#     export_result = handle_export_turn(
#         db,
#         user,
#         probe,
#         session,
#         ui_language=ui_language,
#         exclude_message_id=exclude_id,
#     )
#     if export_result is not None:
#         return export_result
#
#     try:
#         lang = resolve_ui_language(ui_language, user.preferred_language)
#         fedex_facts = None
#         fedex_context = None
#         if tracking:
#             fedex_facts = _prefetch_fedex_context(
#                 db,
#                 user.id,
#                 probe,
#                 resolved_tracking=tracking,
#                 tracking_source=tracking_source,
#             )
#             fedex_context = (fedex_facts.fedex_context_json or None) if fedex_facts else None
#
#         history = load_ollama_history(
#             db,
#             session.id,
#             exclude_message_id=exclude_id,
#         )
#         reply, source = chat_turn(
#             user_message=probe or "(message vide)",
#             history_messages=history,
#             ui_language=ui_language,
#             has_image=has_image,
#         )
#         llm_provider: str | None = "ollama" if source == "ollama" else None
#         if source == "fallback" and fedex_facts is not None:
#             det = fedex_deterministic_reply_if_available(
#                 message=probe,
#                 resolved_tracking=tracking,
#                 fedex_facts=fedex_facts,
#                 fedex_context_json=fedex_context,
#                 preferred_name=kwargs.get("preferred_name"),
#                 ui_language=lang,
#                 reason="ollama_timeout",
#             )
#             if det:
#                 reply = det
#                 source = "deterministic"
#                 llm_provider = "deterministic"
#         reply, tracking_number, shipment_payload = finalize_client_tracking_turn(
#             reply=reply,
#             message=probe,
#             resolved_tracking=tracking,
#             fedex_facts=fedex_facts,
#             fedex_context=fedex_context,
#             tools_used=[],
#             lang=lang,
#             preferred_name=kwargs.get("preferred_name"),
#             conversation_history=history_text,
#             db=db,
#             user=user,
#             session=session,
#         )
#         return ClientTurnResult(
#             reply=reply,
#             source=source,
#             intent="ollama_chat",
#             tracking_number=tracking_number or tracking,
#             shipment=shipment_payload,
#             llm_provider=llm_provider,
#         )
#     except Exception:
#         logger.exception("client_agent kernel run_turn failed")
#         return ClientTurnResult(
#             reply=_FALLBACK_REPLY,
#             source="fallback",
#             intent="error",
#         )
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Noyau client_agent — stub Phase 0."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.client_agent.types import ClientTurnResult


def run_turn(
    db: Session,
    user: User,
    message: str,
    session: ChatSession,
    **kwargs: Any,
) -> ClientTurnResult:
    raise RuntimeError("Phase 0 — assistant client desactive")
