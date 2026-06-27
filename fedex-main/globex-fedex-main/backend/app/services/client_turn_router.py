# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# # =============================================================================
# # LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# # Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# # =============================================================================
# # """Routeur unifié pour les tours de chat client."""
# #
# # from __future__ import annotations
# #
# # from dataclasses import dataclass
# # from typing import Literal
# #
# # from app.services.chat_shipment_reply import classify_shipment_question, is_session_follow_up
# # from app.services.client_agent_service import should_route_to_client_agent
# # from app.services.client_conversational import is_client_conversational_message
# # from app.services.llm.intent_detection import (
# #     detect_intent,
# #     is_general_logistics_question,
# #     is_off_topic_general_question,
# # )
# #
# # TurnType = Literal[
# #     "conversational",
# #     "off_topic_general",
# #     "fedex_general",
# #     "tracking_format",
# #     "tracking_conversational",
# #     "automation",
# # ]
# #
# #
# # @dataclass
# # class ClientTurnPlan:
# #     turn_type: TurnType
# #     intent_out: str
# #     use_fedex: bool
# #     use_agent_tools: bool
# #     use_deterministic_format: bool
# #     strip_tracking_from_history: bool
# #     requires_package_fact_validation: bool
# #     use_off_topic_instruction: bool
# #
# #
# # _STRUCTURED_FORMAT_INTENTS = frozenset(
# #     {
# #         "tabular_history",
# #         "scan_history",
# #         "status_only",
# #         "delivery_eta",
# #         "where_is_package",
# #         "package_details",
# #     }
# # )
# #
# #
# # def _plan(
# #     *,
# #     turn_type: TurnType,
# #     intent_out: str,
# #     use_fedex: bool = False,
# #     use_agent_tools: bool = False,
# #     use_deterministic_format: bool = False,
# #     strip_tracking_from_history: bool = False,
# # ) -> ClientTurnPlan:
# #     requires_validation = turn_type in ("tracking_conversational", "tracking_format", "off_topic_general")
# #     use_off_topic = turn_type == "off_topic_general"
# #     return ClientTurnPlan(
# #         turn_type=turn_type,
# #         intent_out=intent_out,
# #         use_fedex=use_fedex,
# #         use_agent_tools=use_agent_tools,
# #         use_deterministic_format=use_deterministic_format,
# #         strip_tracking_from_history=strip_tracking_from_history,
# #         requires_package_fact_validation=requires_validation,
# #         use_off_topic_instruction=use_off_topic,
# #     )
# #
# #
# # def plan_client_turn(
# #     message: str,
# #     *,
# #     tracking: str | None,
# #     tracking_source: str,
# #     agent_mode: bool = False,
# # ) -> ClientTurnPlan:
# #     """Décide du pipeline pour un tour client."""
# #     msg = (message or "").strip()
# #
# #     if agent_mode or should_route_to_client_agent(msg, tracking_number=tracking):
# #         return _plan(
# #             turn_type="automation",
# #             intent_out="agent",
# #             use_fedex=bool(tracking),
# #             use_agent_tools=True,
# #         )
# #
# #     if is_client_conversational_message(msg):
# #         return _plan(
# #             turn_type="conversational",
# #             intent_out="conversational",
# #             strip_tracking_from_history=True,
# #         )
# #
# #     if is_off_topic_general_question(msg):
# #         return _plan(
# #             turn_type="off_topic_general",
# #             intent_out="off_topic_general",
# #             strip_tracking_from_history=True,
# #         )
# #
# #     if is_general_logistics_question(msg) and not tracking:
# #         return _plan(
# #             turn_type="fedex_general",
# #             intent_out="general_question",
# #             strip_tracking_from_history=True,
# #         )
# #
# #     if tracking:
# #         shipment_intent = classify_shipment_question(msg)
# #         if shipment_intent in _STRUCTURED_FORMAT_INTENTS:
# #             return _plan(
# #                 turn_type="tracking_format",
# #                 intent_out=shipment_intent,
# #                 use_fedex=True,
# #                 use_agent_tools=True,
# #                 use_deterministic_format=True,
# #             )
# #         return _plan(
# #             turn_type="tracking_conversational",
# #             intent_out=shipment_intent if shipment_intent != "summary" else "track_package",
# #             use_fedex=True,
# #             use_agent_tools=True,
# #         )
# #
# #     if is_session_follow_up(msg):
# #         return _plan(
# #             turn_type="tracking_conversational",
# #             intent_out=classify_shipment_question(msg),
# #             use_fedex=True,
# #             use_agent_tools=True,
# #         )
# #
# #     intent = detect_intent(msg, tracking)
# #     if intent == "general_question":
# #         return _plan(
# #             turn_type="fedex_general",
# #             intent_out=intent,
# #             strip_tracking_from_history=True,
# #         )
# #     return _plan(
# #         turn_type="tracking_conversational",
# #         intent_out=intent,
# #         use_fedex=bool(tracking),
# #         use_agent_tools=bool(tracking),
# #     )
# #
# #
# # def off_topic_server_instruction() -> str:
# #     return (
# #         "Question hors suivi colis. Interdit : statut colis, scans, tableau Markdown, hub, ETA, "
# #         "localisation d'expédition, sauf si l'utilisateur demande explicitement un numéro de suivi. "
# #         "Répondez sur le sujet posé (géographie, délais généraux, services FedEx) sans inventer de colis."
# #     )
# #
# #
# # def fedex_general_server_instruction() -> str:
# #     return (
# #         "Question générale FedEx / logistique (pas de colis précis dans ce message). "
# #         "Vous pouvez synthétiser la base de connaissances FedEx. "
# #         "Interdit : inventer un numéro de suivi, un statut, des scans ou un tableau pour un colis précis."
# #     )
# #
# #
# # def conversational_server_instruction() -> str:
# #     return (
# #         "Message conversationnel (salutation, remerciement ou capacités). "
# #         "Répondez brièvement et chaleureusement. Proposez l'aide suivi FedEx sans inventer de colis."
# #     )
# #
# #
# # def server_instruction_for_turn(turn_type: TurnType) -> str | None:
# #     if turn_type == "off_topic_general":
# #         return off_topic_server_instruction()
# #     if turn_type == "fedex_general":
# #         return fedex_general_server_instruction()
# #     if turn_type == "conversational":
# #         return conversational_server_instruction()
# #     return None
# # =============================================================================
# # ACTIVE — Phase 0 stub
# # =============================================================================
# """Routeur client — stub Phase 0."""
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Routeur client — stub Phase 0."""
