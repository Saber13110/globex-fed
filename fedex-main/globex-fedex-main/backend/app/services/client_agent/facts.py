# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """FedEx facts pour un tour client — API serveur avant LLM."""
#
# from __future__ import annotations
#
# import logging
# from dataclasses import dataclass, field
# from typing import Any
#
# from sqlalchemy.orm import Session
#
# from app.core.config import get_settings
# from app.services import fedex_service
# from app.services.chat_shipment_reply import classify_shipment_question
# from app.services.fedex_sandbox_whitelist import (
#     CLIENT_TRACKING_NOT_FOUND_HINT,
#     FedExSandboxWhitelistError,
# )
# from app.services.fedex_service import TrackingLookupError
# from app.services.fedex_visibility_service import (
#     get_pod_record,
#     list_visibility_events,
#     sync_visibility_from_tracking,
#     upsert_pod_from_shipment,
# )
# from app.services.llm.fedex_context import build_shipment_llm_context
# from app.services.proof_of_delivery_service import (
#     get_pod_info_for_tracking,
#     is_likely_delivered,
#     is_pod_available,
# )
# from app.services.shipment_cache_service import upsert_shipment_cache
# from app.services.user_notification_service import maybe_notify_shipment_events
#
# logger = logging.getLogger(__name__)
#
#
# @dataclass
# class FedExTurnFacts:
#     tracking_number: str
#     tracking_source: str
#     intent: str
#     conversation_mode: str = "first_lookup"
#     shipment_data: dict[str, Any] | None = None
#     enrich_ctx: dict[str, Any] = field(default_factory=dict)
#     fedex_context_json: str = ""
#     error_code: str | None = None
#     error_message: str | None = None
#
#
# def _enrich_shipment_context(db: Session, data: dict[str, Any]) -> dict[str, Any]:
#     settings = get_settings()
#     if settings.fedex_visibility_sync_on_track:
#         sync_visibility_from_tracking(db, data, source="tracking_sync", commit=False)
#         if is_likely_delivered(data.get("status"), data.get("events")):
#             upsert_pod_from_shipment(db, data, commit=False)
#     visibility_events = list_visibility_events(db, data["tracking_number"])
#     pod_info = get_pod_info_for_tracking(data, get_pod_record(db, data["tracking_number"]))
#     return {
#         "visibility_events": visibility_events,
#         "pod_info": pod_info,
#         "pod_available": is_pod_available(data),
#     }
#
#
# def fetch_shipment_turn(
#     db: Session,
#     user_id: int,
#     tracking: str,
#     message: str,
#     *,
#     tracking_source: str,
# ) -> FedExTurnFacts:
#     """Appelle FedEx, enrichit le contexte et prépare le JSON pour synthèse LLM."""
#     intent = classify_shipment_question(message)
#     conversation_mode = "follow_up" if tracking_source == "session" else "first_lookup"
#     facts = FedExTurnFacts(
#         tracking_number=tracking.strip().upper(),
#         tracking_source=tracking_source,
#         intent=intent,
#         conversation_mode=conversation_mode,
#     )
#
#     try:
#         shipment_data = fedex_service.get_shipment(tracking)
#         pod_available = is_pod_available(shipment_data)
#         maybe_notify_shipment_events(
#             db,
#             user_id=user_id,
#             data=shipment_data,
#             pod_available=pod_available,
#         )
#         upsert_shipment_cache(db, shipment_data)
#         enrich_ctx = _enrich_shipment_context(db, shipment_data)
#         facts.shipment_data = shipment_data
#         facts.enrich_ctx = enrich_ctx
#         try:
#             facts.fedex_context_json = build_shipment_llm_context(
#                 tracking_number=tracking,
#                 shipment=shipment_data,
#                 visibility_events=enrich_ctx.get("visibility_events"),
#                 pod_info=enrich_ctx.get("pod_info"),
#                 pod_available=enrich_ctx.get("pod_available", False),
#                 user_question_intent=intent,
#                 conversation_mode=conversation_mode,
#             )
#         except (TypeError, ValueError):
#             logger.warning(
#                 "Contexte FedEx JSON incomplet pour %s — repli sans POD/visibilité",
#                 tracking,
#                 exc_info=True,
#             )
#             facts.fedex_context_json = build_shipment_llm_context(
#                 tracking_number=tracking,
#                 shipment=shipment_data,
#                 pod_available=enrich_ctx.get("pod_available", False),
#                 user_question_intent=intent,
#                 conversation_mode=conversation_mode,
#             )
#     except FedExSandboxWhitelistError as exc:
#         facts.error_code = "sandbox_whitelist_denied"
#         facts.error_message = CLIENT_TRACKING_NOT_FOUND_HINT
#         facts.fedex_context_json = build_shipment_llm_context(
#             tracking_number=exc.tracking_number,
#             error_code="sandbox_whitelist_denied",
#             error_message=CLIENT_TRACKING_NOT_FOUND_HINT,
#             user_question_intent=intent,
#             conversation_mode=conversation_mode,
#         )
#     except TrackingLookupError as exc:
#         facts.error_code = "fedex_not_found"
#         facts.error_message = str(exc)
#         facts.fedex_context_json = build_shipment_llm_context(
#             tracking_number=tracking,
#             error_code="fedex_not_found",
#             error_message=str(exc),
#             user_question_intent=intent,
#             conversation_mode=conversation_mode,
#         )
#     except Exception:
#         logger.exception("FedEx indisponible pour %s", tracking)
#         facts.error_code = "fedex_unavailable"
#         facts.error_message = "Le service FedEx est temporairement indisponible."
#         facts.fedex_context_json = build_shipment_llm_context(
#             tracking_number=tracking,
#             error_code="fedex_unavailable",
#             error_message=facts.error_message,
#             user_question_intent=intent,
#             conversation_mode=conversation_mode,
#         )
#
#     return facts
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
