# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Tour client colis — FedEx API + synthèse Ollama + repli déterministe."""
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
# from app.services.chat_shipment_reply import (
#     build_shipment_reply,
#     format_tracking_table_hybrid,
#     shipment_card_display_flags,
#     should_attach_shipment_card,
# )
# from app.services.client_agent.facts import FedExTurnFacts
# from app.services.client_agent.guard import (
#     ensure_error_reply_safe,
#     ensure_shipment_reply_safe,
#     error_fallback_reply,
# )
# from app.services.client_agent.types import ClientTurnResult
# from app.services.gpt.tool_synthesis import synthesize_client_from_fedex_context
# from app.services.tracking_presenter import shipment_summary
# from app.services.tracking_record_service import persist_tracking_request
#
# logger = logging.getLogger(__name__)
#
#
# def _synthesis_llm_provider() -> str:
#     primary = (get_settings().llm_primary_provider or "ollama").strip().lower()
#     return "ollama" if primary == "ollama" else "gemini"
#
#
# def _try_synthesize_from_facts(
#     facts: FedExTurnFacts,
#     message: str,
#     *,
#     ui_language: str | None,
#     preferred_name: str | None,
# ) -> tuple[str, bool]:
#     """Tente une synthèse LLM à partir du JSON FedEx (succès ou erreur)."""
#     settings = get_settings()
#     if settings.use_deterministic_fedex_reply:
#         return "", False
#     try:
#         synthesized = synthesize_client_from_fedex_context(
#             task=message,
#             fedex_context_json=facts.fedex_context_json,
#             ui_language=ui_language or "fr",
#             preferred_name=preferred_name,
#         )
#         if synthesized and synthesized.strip():
#             return synthesized.strip(), True
#     except Exception:
#         logger.warning("synthesize_client_from_fedex_context failed", exc_info=True)
#     return "", False
#
#
# def handle_shipment_turn(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     facts: FedExTurnFacts,
#     **kwargs: Any,
# ) -> ClientTurnResult:
#     """Réponse colis : FedEx d'abord, prose Ollama optionnelle, garde-fous serveur."""
#     ui_language = kwargs.get("ui_language")
#     preferred_name = kwargs.get("preferred_name")
#     intent = facts.intent
#     used_llm = False
#     llm_provider: str | None = None
#
#     if facts.error_code:
#         reply, used_llm = _try_synthesize_from_facts(
#             facts,
#             message,
#             ui_language=ui_language,
#             preferred_name=preferred_name,
#         )
#         if not reply:
#             reply = error_fallback_reply(facts)
#         else:
#             reply = ensure_error_reply_safe(reply, facts)
#         if used_llm:
#             llm_provider = _synthesis_llm_provider()
#         source = "fedex_api+ollama" if used_llm else "fedex_api"
#         return ClientTurnResult(
#             reply=reply,
#             source=source,
#             intent=intent,
#             tracking_number=facts.tracking_number,
#             llm_provider=llm_provider,
#         )
#
#     data = facts.shipment_data
#     enrich = facts.enrich_ctx
#     if not data:
#         return ClientTurnResult(
#             reply="Aucune donnée colis disponible pour ce numéro.",
#             source="fedex_api",
#             intent=intent,
#             tracking_number=facts.tracking_number,
#         )
#
#     deterministic_only = get_settings().use_deterministic_fedex_reply
#
#     try:
#         if intent == "tabular_history":
#             reply, intent, synthesis_used = format_tracking_table_hybrid(
#                 message,
#                 data,
#                 visibility_events=enrich.get("visibility_events"),
#                 pod_info=enrich.get("pod_info"),
#                 pod_available=enrich.get("pod_available", False),
#                 synthesize_intro=not deterministic_only,
#                 ui_language=ui_language,
#                 preferred_name=preferred_name,
#                 fedex_context_json=facts.fedex_context_json,
#             )
#             if synthesis_used:
#                 used_llm = True
#                 llm_provider = _synthesis_llm_provider()
#             reply = ensure_shipment_reply_safe(
#                 reply,
#                 data,
#                 enrich,
#                 message=message,
#                 intent=intent,
#             )
#         else:
#             reply, used_llm = _try_synthesize_from_facts(
#                 facts,
#                 message,
#                 ui_language=ui_language,
#                 preferred_name=preferred_name,
#             )
#             if reply:
#                 reply = ensure_shipment_reply_safe(
#                     reply,
#                     data,
#                     enrich,
#                     message=message,
#                     intent=intent,
#                 )
#                 if used_llm:
#                     llm_provider = _synthesis_llm_provider()
#             if not reply:
#                 reply, intent = build_shipment_reply(
#                     message,
#                     data,
#                     visibility_events=enrich.get("visibility_events"),
#                     pod_info=enrich.get("pod_info"),
#                     pod_available=enrich.get("pod_available", False),
#                 )
#                 used_llm = False
#                 llm_provider = None
#     except Exception:
#         logger.exception("handle_shipment_turn failed for %s", facts.tracking_number)
#         reply, intent = build_shipment_reply(
#             message,
#             data,
#             visibility_events=enrich.get("visibility_events"),
#             pod_info=enrich.get("pod_info"),
#             pod_available=enrich.get("pod_available", False),
#         )
#         used_llm = False
#         llm_provider = None
#
#     shipment_payload: dict[str, Any] | None = None
#     if should_attach_shipment_card(
#         intent=intent,
#         tracking_source=facts.tracking_source,
#         pod_available=enrich.get("pod_available", False),
#     ):
#         flags = shipment_card_display_flags(intent)
#         shipment_payload = shipment_summary(
#             data,
#             extras=enrich,
#             show_tracking_map=bool(flags.get("show_tracking_map")),
#             show_timeline=bool(flags.get("show_timeline")),
#             max_timeline_events=int(flags.get("max_timeline_events") or 0),
#         )
#
#     source = "fedex_api+ollama" if used_llm else "fedex_api"
#     try:
#         persist_tracking_request(
#             db,
#             user_id=user.id,
#             session_id=session.id,
#             tracking_number=facts.tracking_number,
#             user_question=message,
#             bot_response=reply,
#             shipment_data=data,
#         )
#     except Exception:
#         logger.warning("persist_tracking_request failed for %s", facts.tracking_number, exc_info=True)
#
#     return ClientTurnResult(
#         reply=reply,
#         source=source,
#         intent=intent,
#         tracking_number=facts.tracking_number,
#         llm_provider=llm_provider,
#         shipment=shipment_payload,
#     )
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
