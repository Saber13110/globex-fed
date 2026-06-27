# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# # =============================================================================
# # LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# # Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# # =============================================================================
# # import logging
# # from dataclasses import dataclass
# # from typing import Any
# #
# # from sqlalchemy import func
# # from sqlalchemy.orm import Session
# #
# # from app.models.chat_message import ChatMessage, MessageSender
# # from app.models.chat_session import ChatSession
# # from app.models.tracking_request import TrackingRequest
# # from app.models.user import User
# # from app.core.config import get_settings
# # from app.services import fedex_service, llm_service
# # from app.services.chat_export_service import handle_chat_export_request
# # from app.services.chat_session_context import (
# #     build_conversation_history_for_llm,
# #     resolve_tracking_for_message,
# # )
# # from app.services.chat_shipment_reply import (
# #     INTENT_MAP_TRACKING,
# #     build_shipment_reply,
# #     classify_shipment_question,
# #     format_tracking_table_hybrid,
# #     is_session_follow_up,
# #     should_attach_shipment_card,
# #     shipment_card_display_flags,
# # )
# # from app.services.client_response_validator import should_validate_turn, validate_client_reply
# # from app.services.client_conversational import (
# #     client_capabilities_reply,
# #     client_greeting_reply,
# #     is_client_capabilities_message,
# #     is_client_greeting_only,
# # )
# # from app.services.client_turn_router import (
# #     ClientTurnPlan,
# #     plan_client_turn,
# #     server_instruction_for_turn,
# # )
# # from app.services.llm.intent_detection import detect_intent, is_general_logistics_question
# # from app.services.fedex_sandbox_whitelist import (
# #     CLIENT_TRACKING_NOT_FOUND_HINT,
# #     FedExSandboxWhitelistError,
# #     SANDBOX_WHITELIST_MESSAGE,
# # )
# # from app.services.fedex_visibility_service import (
# #     get_pod_record,
# #     list_visibility_events,
# #     sync_visibility_from_tracking,
# #     upsert_pod_from_shipment,
# # )
# # from app.services.proof_of_delivery_service import (
# #     get_pod_info_for_tracking,
# #     is_likely_delivered,
# #     is_pod_available,
# # )
# # from app.services.llm.fedex_context import build_shipment_llm_context
# # from app.services.llm.session_title import heuristic_session_title, should_auto_rename
# # from app.services.message_attachment import normalize_image_mime, pack_message_text
# # from app.services.llm.prompts import prompt_injection_refusal
# # from app.services.prompt_guard_service import (
# #     RiskLevel,
# #     assess_user_message,
# #     filter_model_output,
# #     must_block_preferences,
# # )
# # from app.services.tracking_presenter import shipment_summary
# # from app.services.user_notification_service import maybe_notify_shipment_events
# # from app.services.client_agent_service import (
# #     TASK_PICKER,
# #     detect_agent_task,
# #     is_simple_tracking_request,
# #     process_agent_message,
# #     should_route_to_client_agent,
# # )
# # from app.services.shipment_cache_service import upsert_shipment_cache
# #
# # logger = logging.getLogger(__name__)
# #
# # _STRUCTURED_SHIPMENT_INTENTS = frozenset(
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
# # @dataclass
# # class _ClientShipmentContext:
# #     tracking: str | None
# #     tracking_source: str
# #     intent_out: str
# #     conversation_mode: str
# #     shipment_data: dict[str, Any] | None
# #     enrich_ctx: dict[str, Any] | None
# #     fedex_context_json: str | None
# #     tracking_error_code: str | None
# #     shipment_for_client: dict[str, Any] | None
# #     skip_fedex_fetch: bool
# #
# #
# # def _strip_active_tracking_header(conversation_history: str | None) -> str | None:
# #     if not conversation_history:
# #         return conversation_history
# #     lines = [
# #         line
# #         for line in conversation_history.splitlines()
# #         if not line.strip().startswith("[Colis actif dans cette conversation")
# #     ]
# #     cleaned = "\n".join(lines).strip()
# #     return cleaned or None
# #
# #
# # def _trim_conversation_history(
# #     conversation_history: str | None,
# #     *,
# #     max_lines: int = 8,
# # ) -> str | None:
# #     if not conversation_history:
# #         return None
# #     lines = [line for line in conversation_history.splitlines() if line.strip()]
# #     if len(lines) <= max_lines:
# #         return conversation_history
# #     return "\n".join(lines[-max_lines:])
# #
# #
# # def _apply_client_validator(
# #     reply: str,
# #     *,
# #     message: str,
# #     fedex_context_json: str | None,
# #     intent: str | None,
# #     ui_language: str | None,
# #     preferred_name: str | None,
# #     tools_used: list[str] | None = None,
# #     tool_payloads: list[dict[str, Any]] | None = None,
# #     turn_plan: ClientTurnPlan | None = None,
# # ) -> tuple[str, bool, str | None]:
# #     turn_type = turn_plan.turn_type if turn_plan else None
# #     if not should_validate_turn(turn_type):
# #         return reply, False, None
# #
# #     validated, blocked, reason = validate_client_reply(
# #         reply,
# #         message=message,
# #         fedex_context_json=fedex_context_json,
# #         tool_payloads=tool_payloads,
# #         intent=intent,
# #         ui_language=ui_language,
# #         preferred_name=preferred_name,
# #         tools_used=tools_used,
# #         turn_type=turn_type,
# #     )
# #     if blocked:
# #         logger.info(
# #             "client_validator_blocked turn_type=%s intent=%s reason=%s tools=%s fedex=%s",
# #             turn_type,
# #             intent,
# #             reason,
# #             tools_used or [],
# #             bool(fedex_context_json),
# #         )
# #     return validated, blocked, reason
# #
# #
# # def _resolve_tracking_intent(
# #     message: str,
# #     *,
# #     tracking: str | None,
# #     tracking_source: str,
# # ) -> str:
# #     intent = detect_intent(message, tracking)
# #     if is_general_logistics_question(message):
# #         return "general_question"
# #     if tracking:
# #         return classify_shipment_question(message)
# #     if is_session_follow_up(message):
# #         return classify_shipment_question(message)
# #     return intent
# #
# #
# # def _append_active_tracking_header(conversation_history: str | None, tracking: str) -> str:
# #     header = f"[Colis actif dans cette conversation : {tracking}]"
# #     if conversation_history:
# #         return f"{header}\n{conversation_history}"
# #     return header
# #
# #
# # def _load_client_shipment_context(
# #     db: Session,
# #     user: User,
# #     *,
# #     tracking: str,
# #     tracking_source: str,
# #     message: str,
# #     intent_out: str,
# # ) -> _ClientShipmentContext:
# #     conversation_mode = "follow_up" if tracking_source == "session" else "first_lookup"
# #     shipment_data: dict[str, Any] | None = None
# #     enrich_ctx: dict[str, Any] | None = None
# #     fedex_context_json: str | None = None
# #     skip_fedex_fetch = False
# #     shipment_for_client: dict[str, Any] | None = None
# #     tracking_error_code: str | None = None
# #     resolved_intent = intent_out
# #
# #     try:
# #         shipment_data = fedex_service.get_shipment(tracking)
# #         pod_available = _pod_available_for_shipment(shipment_data)
# #         maybe_notify_shipment_events(
# #             db,
# #             user_id=user.id,
# #             data=shipment_data,
# #             pod_available=pod_available,
# #         )
# #         upsert_shipment_cache(db, shipment_data)
# #         enrich_ctx = _enrich_shipment_context(db, shipment_data)
# #         fedex_context_json = build_shipment_llm_context(
# #             tracking_number=tracking,
# #             shipment=shipment_data,
# #             visibility_events=enrich_ctx.get("visibility_events"),
# #             pod_info=enrich_ctx.get("pod_info"),
# #             pod_available=enrich_ctx.get("pod_available", False),
# #             user_question_intent=resolved_intent,
# #             conversation_mode=conversation_mode,
# #         )
# #         skip_fedex_fetch = True
# #         if should_attach_shipment_card(
# #             intent=resolved_intent,
# #             tracking_source=tracking_source,
# #             pod_available=enrich_ctx.get("pod_available", False),
# #         ):
# #             display_flags = shipment_card_display_flags(resolved_intent)
# #             shipment_for_client = shipment_summary(
# #                 shipment_data,
# #                 extras=enrich_ctx,
# #                 **display_flags,
# #             )
# #     except FedExSandboxWhitelistError as exc:
# #         tracking_error_code = "sandbox_whitelist_denied"
# #         fedex_context_json = build_shipment_llm_context(
# #             tracking_number=exc.tracking_number,
# #             error_code="sandbox_whitelist_denied",
# #             error_message=CLIENT_TRACKING_NOT_FOUND_HINT,
# #             user_question_intent="track_package",
# #         )
# #         skip_fedex_fetch = True
# #         resolved_intent = "sandbox_whitelist_denied"
# #         if tracking_source == "message":
# #             shipment_for_client = {
# #                 "tracking_number": exc.tracking_number,
# #                 "sandbox_whitelist_denied": True,
# #                 "status": None,
# #                 "current_location": None,
# #                 "estimated_delivery": None,
# #             }
# #     except fedex_service.TrackingLookupError as exc:
# #         tracking_error_code = "fedex_not_found"
# #         fedex_context_json = build_shipment_llm_context(
# #             tracking_number=tracking,
# #             error_code="fedex_not_found",
# #             error_message=str(exc),
# #             user_question_intent="track_package",
# #         )
# #         skip_fedex_fetch = True
# #     except Exception:
# #         logger.exception("FedEx indisponible pour %s", tracking)
# #         fedex_context_json = build_shipment_llm_context(
# #             tracking_number=tracking,
# #             error_code="fedex_unavailable",
# #             error_message="Le service FedEx est temporairement indisponible.",
# #         )
# #         skip_fedex_fetch = True
# #
# #     return _ClientShipmentContext(
# #         tracking=tracking,
# #         tracking_source=tracking_source,
# #         intent_out=resolved_intent,
# #         conversation_mode=conversation_mode,
# #         shipment_data=shipment_data,
# #         enrich_ctx=enrich_ctx,
# #         fedex_context_json=fedex_context_json,
# #         tracking_error_code=tracking_error_code,
# #         shipment_for_client=shipment_for_client,
# #         skip_fedex_fetch=skip_fedex_fetch,
# #     )
# #
# #
# # def _deterministic_shipment_reply_if_applicable(
# #     message: str,
# #     ctx: _ClientShipmentContext,
# #     *,
# #     ui_language: str | None = None,
# #     preferred_name: str | None = None,
# # ) -> tuple[str, str, str | None] | None:
# #     if not ctx.shipment_data or not ctx.enrich_ctx:
# #         return None
# #     if ctx.intent_out not in _STRUCTURED_SHIPMENT_INTENTS:
# #         return None
# #     if ctx.intent_out == "tabular_history":
# #         reply, intent, intro_provider = format_tracking_table_hybrid(
# #             message,
# #             ctx.shipment_data,
# #             visibility_events=ctx.enrich_ctx.get("visibility_events"),
# #             pod_info=ctx.enrich_ctx.get("pod_info"),
# #             pod_available=ctx.enrich_ctx.get("pod_available", False),
# #             fedex_context_json=ctx.fedex_context_json,
# #             ui_language=ui_language,
# #             preferred_name=preferred_name,
# #         )
# #         return reply, intent, intro_provider
# #     reply, intent = build_shipment_reply(
# #         message,
# #         ctx.shipment_data,
# #         visibility_events=ctx.enrich_ctx.get("visibility_events"),
# #         pod_info=ctx.enrich_ctx.get("pod_info"),
# #         pod_available=ctx.enrich_ctx.get("pod_available", False),
# #     )
# #     return reply, intent, None
# #
# #
# # def _resolve_client_tracking_context(
# #     db: Session,
# #     user: User,
# #     session: ChatSession,
# #     message: str,
# #     conversation_history: str | None,
# #     *,
# #     turn_plan: ClientTurnPlan | None = None,
# # ) -> tuple[_ClientShipmentContext, str | None, str | None, ClientTurnPlan]:
# #     """Résout numéro de session, intent et contexte FedEx pour le chat client."""
# #     from app.services.llm.fedex_context import (
# #         client_tracking_server_instruction,
# #         resolve_client_fedex_lookup,
# #     )
# #
# #     tracking, tracking_source = resolve_tracking_for_message(
# #         db,
# #         session_id=session.id,
# #         user_id=user.id,
# #         message=message,
# #         conversation_history=conversation_history,
# #     )
# #     plan = turn_plan or plan_client_turn(
# #         message,
# #         tracking=tracking,
# #         tracking_source=tracking_source,
# #     )
# #
# #     hist = conversation_history
# #     server_instruction: str | None = None
# #
# #     if plan.strip_tracking_from_history:
# #         tracking = None
# #         tracking_source = "none"
# #         hist = _strip_active_tracking_header(hist)
# #         hist = _trim_conversation_history(hist)
# #         server_instruction = server_instruction_for_turn(plan.turn_type)
# #         empty = _ClientShipmentContext(
# #             tracking=None,
# #             tracking_source=tracking_source,
# #             intent_out=plan.intent_out,
# #             conversation_mode="first_lookup",
# #             shipment_data=None,
# #             enrich_ctx=None,
# #             fedex_context_json=None,
# #             tracking_error_code=None,
# #             shipment_for_client=None,
# #             skip_fedex_fetch=False,
# #         )
# #         return empty, hist, server_instruction, plan
# #
# #     if tracking and tracking_source == "session":
# #         hist = _append_active_tracking_header(hist, tracking)
# #
# #     intent_out = plan.intent_out
# #
# #     if not tracking or not plan.use_fedex:
# #         empty = _ClientShipmentContext(
# #             tracking=None,
# #             tracking_source=tracking_source,
# #             intent_out=intent_out,
# #             conversation_mode="first_lookup",
# #             shipment_data=None,
# #             enrich_ctx=None,
# #             fedex_context_json=None,
# #             tracking_error_code=None,
# #             shipment_for_client=None,
# #             skip_fedex_fetch=False,
# #         )
# #         return empty, hist, server_instruction, plan
# #
# #     ctx = _load_client_shipment_context(
# #         db,
# #         user,
# #         tracking=tracking,
# #         tracking_source=tracking_source,
# #         message=message,
# #         intent_out=intent_out,
# #     )
# #     server_instruction = client_tracking_server_instruction(
# #         tracking_number=tracking,
# #         tracking_error_code=ctx.tracking_error_code,
# #     )
# #     if ctx.fedex_context_json and ctx.tracking_error_code is None:
# #         lookup = resolve_client_fedex_lookup(
# #             tracking,
# #             user_question_intent=ctx.intent_out,
# #             conversation_mode=ctx.conversation_mode,
# #         )
# #         ctx.fedex_context_json = lookup.fedex_context_json
# #     return ctx, hist, server_instruction, plan
# #
# #
# # def _safe_reply(text: str) -> str:
# #     out, redacted = filter_model_output(text or "")
# #     if redacted:
# #         logger.warning("Réponse LLM partiellement masquée (filtre sécurité)")
# #     return out
# #
# #
# # _EXPORT_TRIGGERS = (
# #     "export",
# #     "excel",
# #     "xlsx",
# #     "telecharger",
# #     "télécharger",
# #     "fichier",
# #     "historique",
# # )
# #
# #
# # def _is_pod_request(text: str) -> bool:
# #     from app.services.chat_shipment_reply import is_pod_request as _pod
# #
# #     return _pod(text)
# #
# #
# # def _pod_available_for_shipment(data: dict[str, Any]) -> bool:
# #     return is_pod_available(data)
# #
# #
# # def _enrich_shipment_context(db: Session, data: dict[str, Any]) -> dict[str, Any]:
# #     settings = get_settings()
# #     if settings.fedex_visibility_sync_on_track:
# #         sync_visibility_from_tracking(db, data, source="tracking_sync", commit=False)
# #         if is_likely_delivered(data.get("status"), data.get("events")):
# #             upsert_pod_from_shipment(db, data, commit=False)
# #     visibility_events = list_visibility_events(db, data["tracking_number"])
# #     pod_info = get_pod_info_for_tracking(data, get_pod_record(db, data["tracking_number"]))
# #     return {
# #         "visibility_events": visibility_events,
# #         "pod_info": pod_info,
# #         "pod_available": _pod_available_for_shipment(data),
# #     }
# #
# #
# # def _apply_session_title(
# #     session: ChatSession,
# #     user_message: str,
# #     *,
# #     bot_reply: str | None = None,
# #     ui_language: str | None = None,
# #     intent: str | None = None,
# #     tracking_number: str | None = None,
# #     has_image: bool = False,
# # ) -> None:
# #     if not should_auto_rename(session.title):
# #         return
# #     try:
# #         session.title = llm_service.generate_session_title(
# #             user_message,
# #             bot_reply=bot_reply,
# #             ui_language=ui_language,
# #             intent=intent,
# #             tracking_number=tracking_number,
# #             has_image=has_image,
# #         )
# #     except Exception:
# #         session.title = heuristic_session_title(
# #             user_message,
# #             ui_language=ui_language,
# #             intent=intent,
# #             tracking_number=tracking_number,
# #             has_image=has_image,
# #         )
# #
# #
# # def _base_result(
# #     reply: str,
# #     session: ChatSession,
# #     *,
# #     shipment: dict[str, Any] | None = None,
# #     source: str,
# #     intent: str,
# #     tracking_number: str | None,
# #     llm_provider: str | None,
# # ) -> dict[str, Any]:
# #     return {
# #         "reply": reply,
# #         "session_id": session.id,
# #         "session_title": session.title,
# #         "shipment": shipment,
# #         "source": source,
# #         "intent": intent,
# #         "tracking_number": tracking_number,
# #         "llm_provider": llm_provider,
# #     }
# #
# #
# # def _apply_mock_watch_subscription(
# #     db: Session,
# #     user: User,
# #     mock: dict[str, Any],
# # ) -> dict[str, Any]:
# #     """Active réellement la surveillance + envoi e-mail pour le scénario mock watch."""
# #     if mock.get("mock_scenario") != "agent_watch_email":
# #         return mock
# #
# #     tn = str(mock.get("tracking_number") or "").strip()
# #     if not tn:
# #         return mock
# #
# #     from app.services.email_service import is_email_configured
# #     from app.services.fedex_sandbox_whitelist import FedExSandboxWhitelistError
# #     from app.services.shipment_watch_service import activate_client_shipment_watch
# #
# #     reply = str(mock.get("reply") or "")
# #     email = (user.email or "").strip()
# #
# #     try:
# #         outcome = activate_client_shipment_watch(
# #             db,
# #             user=user,
# #             tracking_number=tn,
# #             notify_email=True,
# #             notify_in_app=True,
# #         )
# #         if outcome.get("confirmation_sent") and email:
# #             reply += (
# #                 f"\n\nUn e-mail de **confirmation** vient d'être envoyé à `{email}`."
# #             )
# #         elif not is_email_configured():
# #             reply += (
# #                 "\n\n_Note : le serveur e-mail (SMTP) n'est pas configuré — "
# #                 "contactez l'administrateur pour activer les alertes par mail._"
# #             )
# #         elif email:
# #             reply += (
# #                 f"\n\n_L'e-mail de confirmation n'a pas pu être envoyé à `{email}` "
# #                 "(vérifiez la configuration SMTP)._"
# #             )
# #         else:
# #             reply += "\n\n_Aucune adresse e-mail sur votre compte — alertes uniquement dans l'app._"
# #
# #         if outcome.get("alert_sent"):
# #             reply += (
# #                 "\n\nUne **première alerte** de changement de localisation vient aussi "
# #                 "d'être envoyée par e-mail (simulation sandbox FedEx)."
# #             )
# #         else:
# #             settings = get_settings()
# #             interval = max(60, int(settings.shipment_watch_interval_seconds or 60))
# #             reply += (
# #                 f"\n\nLes prochaines alertes e-mail arrivent automatiquement "
# #                 f"(vérification toutes les {interval // 60} min)."
# #             )
# #     except FedExSandboxWhitelistError:
# #         reply += (
# #             f"\n\n_Surveillance impossible pour `{tn}` : numéro hors whitelist sandbox FedEx._"
# #         )
# #     except Exception:
# #         logger.exception("Échec activation surveillance mock pour %s", tn)
# #         reply += (
# #             "\n\n_L'activation de la surveillance a échoué — réessayez ou contactez le support._"
# #         )
# #
# #     return {**mock, "reply": reply}
# #
# #
# # def _apply_mock_support_ticket(
# #     db: Session,
# #     user: User,
# #     mock: dict[str, Any],
# #     *,
# #     original_message: str,
# # ) -> dict[str, Any]:
# #     """Crée un vrai ticket support pour le scénario mock admin/ticket."""
# #     if mock.get("mock_scenario") != "agent_support_ticket":
# #         return mock
# #
# #     from app.services.client_agent_service import open_client_support_ticket
# #
# #     body = str(mock.get("support_message") or original_message or "").strip()
# #     tn = str(mock.get("tracking_number") or "").strip() or None
# #     reply = str(mock.get("reply") or "")
# #     opened: dict[str, Any] | None = None
# #
# #     try:
# #         opened = open_client_support_ticket(
# #             db,
# #             user=user,
# #             message=body,
# #             tracking_number=tn,
# #             priority="medium",
# #             subject_prefix="[Chat client]",
# #         )
# #         ticket_no = opened["ticket_number"]
# #         reply = (
# #             f"{reply.rstrip()}\n\n"
# #             f"**Ticket ouvert** — référence `{ticket_no}`.\n"
# #             "L'équipe admin a été **notifiée** et pourra vérifier pourquoi vous ne "
# #             "recevez pas les e-mails de suivi.\n\n"
# #             "Suivez l'avancement dans **Aide → Mes tickets**."
# #         )
# #     except Exception:
# #         logger.exception("Échec création ticket support mock")
# #         reply += (
# #             "\n\n_L'ouverture du ticket a échoué — réessayez ou contactez le support via le menu Aide._"
# #         )
# #
# #     if opened:
# #         mock = {**mock, "tracking_number": opened.get("tracking_number") or mock.get("tracking_number")}
# #     return {**mock, "reply": reply}
# #
# #
# # def _finalize_mock_chat_turn(
# #     db: Session,
# #     user: User,
# #     session: ChatSession,
# #     message: str,
# #     mock: dict[str, Any],
# #     *,
# #     ui_language: str | None = None,
# # ) -> dict[str, Any]:
# #     """Persiste user/bot et retourne le payload API (mode mock, sans LLM)."""
# #     mock = _apply_mock_watch_subscription(db, user, mock)
# #     mock = _apply_mock_support_ticket(db, user, mock, original_message=message)
# #     stored_message = pack_message_text(message, image_base64=None, image_mime_type=None)
# #     user_msg = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.user.value,
# #         source="user_input",
# #         message_text=stored_message,
# #     )
# #     db.add(user_msg)
# #     db.flush()
# #
# #     reply = str(mock.get("reply") or "")
# #     bot = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.bot.value,
# #         source=str(mock.get("source") or "mock"),
# #         message_text=reply,
# #     )
# #     db.add(bot)
# #
# #     intent_out = str(mock.get("intent") or "mock")
# #     tracking = mock.get("tracking_number")
# #     if should_auto_rename(session.title):
# #         session.title = heuristic_session_title(
# #             message,
# #             ui_language=ui_language,
# #             intent=intent_out,
# #             tracking_number=tracking,
# #         )
# #     session.updated_at = func.now()
# #     db.commit()
# #     db.refresh(bot)
# #
# #     export_dl = mock.get("export_download")
# #     if isinstance(export_dl, dict):
# #         sid = export_dl.get("session_id")
# #         if sid is None or sid == 0:
# #             mock = {**mock, "export_download": {**export_dl, "session_id": session.id}}
# #
# #     result = _base_result(
# #         reply,
# #         session,
# #         shipment=mock.get("shipment"),
# #         source=str(mock.get("source") or "mock"),
# #         intent=intent_out,
# #         tracking_number=tracking,
# #         llm_provider=mock.get("llm_provider"),
# #     )
# #     for key in (
# #         "agent_mode",
# #         "agent_phase",
# #         "agent_steps",
# #         "agent_questionnaire",
# #         "agent_reasoning",
# #         "export_download",
# #         "mock_scenario",
# #     ):
# #         if key in mock:
# #             result[key] = mock[key]
# #     return result
# #
# #
# # def _should_auto_run_agent(message: str) -> bool:
# #     """Route automatiquement les demandes FedEx automatisables (sans toggle Agent)."""
# #     return should_route_to_client_agent(message)
# #
# #
# # def process_user_message(
# #     db: Session,
# #     user: User,
# #     message: str,
# #     session: ChatSession,
# #     response_preferences: str | None = None,
# #     preferred_name: str | None = None,
# #     ui_language: str | None = None,
# #     image_base64: str | None = None,
# #     image_mime_type: str | None = None,
# #     agent_mode: bool = False,
# #     agent_flow_id: str | None = None,
# #     agent_answers: dict[str, str] | None = None,
# # ) -> dict[str, Any]:
# #     settings = get_settings()
# #     probe_text = (message or "").strip()
# #     if settings.prompt_guard_enabled and probe_text and not (image_base64 or "").strip():
# #         risk = assess_user_message(probe_text)
# #         if must_block_preferences(risk):
# #             lang = (ui_language or user.preferred_language or "fr").lower()
# #             refusal = prompt_injection_refusal(lang)
# #             return {
# #                 "reply": refusal,
# #                 "session_id": session.id,
# #                 "session_title": session.title,
# #                 "source": "security",
# #                 "intent": "security_blocked",
# #                 "tracking_number": None,
# #                 "llm_provider": None,
# #                 "shipment": None,
# #                 "agent_mode": False,
# #             }
# #
# #     if (
# #         settings.mock_client_chat_enabled
# #         and probe_text
# #         and not (image_base64 or "").strip()
# #         and not agent_flow_id
# #         and not agent_answers
# #     ):
# #         from app.services.client_chat_mock import try_mock_client_response
# #
# #         will_agent = bool(agent_mode) or _should_auto_run_agent(message)
# #         conversation_history = build_conversation_history_for_llm(db, session_id=session.id)
# #         mock = try_mock_client_response(
# #             message,
# #             agent_mode=will_agent,
# #             preferred_name=preferred_name or user.full_name,
# #             conversation_history=conversation_history,
# #             session_id=session.id,
# #         )
# #         if mock:
# #             return _finalize_mock_chat_turn(
# #                 db,
# #                 user,
# #                 session,
# #                 message,
# #                 mock,
# #                 ui_language=ui_language,
# #             )
# #
# #     if not (agent_mode or agent_flow_id) and _should_auto_run_agent(message):
# #         return _process_agent_user_message(
# #             db,
# #             user,
# #             message,
# #             session,
# #             ui_language=ui_language,
# #             agent_flow_id=agent_flow_id,
# #             agent_answers=agent_answers,
# #             has_image=bool((image_base64 or "").strip()),
# #         )
# #
# #     if agent_mode or agent_flow_id:
# #         return _process_agent_user_message(
# #             db,
# #             user,
# #             message,
# #             session,
# #             ui_language=ui_language,
# #             agent_flow_id=agent_flow_id,
# #             agent_answers=agent_answers,
# #             has_image=bool((image_base64 or "").strip()),
# #         )
# #
# #     preview_plan: ClientTurnPlan | None = None
# #     if not (image_base64 or "").strip():
# #         hist_preview = build_conversation_history_for_llm(db, session_id=session.id)
# #         tr_preview, tr_src_preview = resolve_tracking_for_message(
# #             db,
# #             session_id=session.id,
# #             user_id=user.id,
# #             message=message,
# #             conversation_history=hist_preview,
# #         )
# #         preview_plan = plan_client_turn(
# #             message,
# #             tracking=tr_preview,
# #             tracking_source=tr_src_preview,
# #         )
# #         if preview_plan.turn_type == "conversational" and is_client_greeting_only(message):
# #             return _process_conversational_turn(
# #                 db,
# #                 user,
# #                 message,
# #                 session,
# #                 ui_language=ui_language,
# #                 preferred_name=preferred_name,
# #                 turn_plan=preview_plan,
# #             )
# #         if preview_plan.turn_type in ("tracking_conversational", "tracking_format"):
# #             if settings.gpt_tools_enabled and settings.llm_enabled:
# #                 return _process_client_tracking_turn(
# #                     db,
# #                     user,
# #                     message,
# #                     session,
# #                     ui_language=ui_language,
# #                     preferred_name=preferred_name,
# #                     turn_plan=preview_plan,
# #                 )
# #
# #     mime = normalize_image_mime(image_mime_type)
# #     b64 = (image_base64 or "").strip() or None
# #     if b64 and not mime:
# #         b64 = None
# #     has_image = bool(b64)
# #     stored_message = pack_message_text(message, image_base64=b64, image_mime_type=mime)
# #
# #     user_msg = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.user.value,
# #         source="user_input",
# #         message_text=stored_message,
# #     )
# #     db.add(user_msg)
# #     db.flush()
# #
# #     export_result = handle_chat_export_request(
# #         db,
# #         session,
# #         user,
# #         message,
# #         safe_reply_fn=_safe_reply,
# #         apply_title_fn=lambda sess, msg, **kwargs: _apply_session_title(
# #             sess, msg, ui_language=ui_language, **kwargs
# #         ),
# #         base_result_fn=lambda reply, sess, **kwargs: _base_result(reply, sess, **kwargs),
# #     )
# #     if export_result is not None:
# #         return export_result
# #
# #     conversation_history = build_conversation_history_for_llm(
# #         db,
# #         session_id=session.id,
# #         exclude_message_id=user_msg.id,
# #     )
# #
# #     ship_ctx, conversation_history, server_instruction, turn_plan = _resolve_client_tracking_context(
# #         db,
# #         user,
# #         session,
# #         message,
# #         conversation_history,
# #         turn_plan=preview_plan,
# #     )
# #     tracking = ship_ctx.tracking
# #     tracking_source = ship_ctx.tracking_source
# #     intent_out = ship_ctx.intent_out
# #     shipment_data = ship_ctx.shipment_data
# #     enrich_ctx = ship_ctx.enrich_ctx
# #     fedex_context_json = ship_ctx.fedex_context_json if turn_plan.use_fedex else None
# #     skip_fedex_fetch = ship_ctx.skip_fedex_fetch
# #     shipment_for_client = ship_ctx.shipment_for_client
# #     tracking_error_code = ship_ctx.tracking_error_code
# #
# #     deterministic = _deterministic_shipment_reply_if_applicable(
# #         message,
# #         ship_ctx,
# #         ui_language=ui_language,
# #         preferred_name=preferred_name,
# #     )
# #     reply: str | None = None
# #     source: str | None = None
# #     llm_provider: str | None = None
# #     intent = intent_out
# #     validator_blocked = False
# #     validator_reason: str | None = None
# #
# #     if deterministic:
# #         reply, intent_out, intro_provider = deterministic
# #         source = "fedex_api"
# #         llm_provider = intro_provider
# #
# #     if reply is None:
# #         try:
# #             from app.services.gpt.orchestrator import SLUG_CLIENT, run_gpt_turn
# #
# #             turn = run_gpt_turn(
# #                 db,
# #                 gpt_slug=SLUG_CLIENT,
# #                 user_id=user.id,
# #                 message=message,
# #                 session_id=session.id,
# #                 ui_language=ui_language,
# #                 profile_language=user.preferred_language,
# #                 fedex_context=fedex_context_json,
# #                 response_preferences=response_preferences,
# #                 preferred_name=preferred_name,
# #                 image_base64=b64,
# #                 image_mime_type=mime,
# #                 conversation_history=conversation_history or None,
# #                 exclude_message_id=user_msg.id,
# #                 server_instruction=server_instruction,
# #             )
# #             reply = turn.reply
# #             llm_provider = turn.llm_provider
# #             source = llm_provider if llm_provider in {"gemini", "ollama"} else "llm"
# #             if tracking:
# #                 intent_out = turn.intent or intent_out
# #             else:
# #                 intent = turn.intent
# #                 intent_out = intent
# #             from app.services.llm.tracking_extract import extract_tracking_number
# #
# #             extracted = extract_tracking_number(message)
# #             if extracted:
# #                 tracking = extracted
# #         except Exception:
# #             logger.debug("GPT runtime indisponible, repli orchestrateur classique", exc_info=True)
# #             try:
# #                 llm_result = llm_service.generate_response(
# #                     message,
# #                     response_preferences=response_preferences,
# #                     preferred_name=preferred_name,
# #                     ui_language=ui_language,
# #                     image_base64=b64,
# #                     image_mime_type=mime,
# #                     fedex_context_json=fedex_context_json,
# #                     skip_fedex_fetch=skip_fedex_fetch,
# #                     force_intent=intent_out if tracking or is_session_follow_up(message) else None,
# #                     conversation_history=conversation_history or None,
# #                 )
# #                 reply = llm_result.reply
# #                 llm_provider = llm_result.llm_provider
# #                 source = llm_provider if llm_provider in {"gemini", "ollama"} else "llm"
# #                 if tracking:
# #                     intent_out = llm_result.intent or intent_out
# #                     tracking = llm_result.tracking_number or tracking
# #                 else:
# #                     intent = llm_result.intent
# #                     tracking = llm_result.tracking_number
# #                     intent_out = intent
# #             except Exception as exc:
# #                 logger.exception("LLM indisponible: %s", exc)
# #                 if shipment_data and enrich_ctx:
# #                     reply, intent_out = build_shipment_reply(
# #                         message,
# #                         shipment_data,
# #                         visibility_events=enrich_ctx.get("visibility_events"),
# #                         pod_info=enrich_ctx.get("pod_info"),
# #                         pod_available=enrich_ctx.get("pod_available", False),
# #                     )
# #                     source = "fallback"
# #                     llm_provider = None
# #                 elif tracking:
# #                     reply = (
# #                         "Le service d'assistance IA est momentanément indisponible "
# #                         "(Gemini et Ollama). Les données FedEx ont été récupérées mais je ne peux pas "
# #                         "formuler la réponse pour le moment. Réessayez dans quelques instants."
# #                     )
# #                     source = "fallback"
# #                     llm_provider = None
# #                 elif intent == "general_question":
# #                     name = (preferred_name or "").strip()
# #                     greeting = f"Bonjour {name}," if name else "Bonjour,"
# #                     primary = (settings.llm_primary_provider or "ollama").strip().lower()
# #                     if primary == "ollama":
# #                         reply = (
# #                             f"{greeting} le service d'assistance IA est momentanément indisponible. "
# #                             "Ollama ne répond pas — vérifiez qu'il tourne sur le port 11434 "
# #                             f"({settings.ollama_base_url}) et que le modèle « {settings.ollama_model} » est installé."
# #                         )
# #                     else:
# #                         reply = (
# #                             f"{greeting} le service d'assistance IA est momentanément indisponible "
# #                             "(Gemini et Ollama). Réessayez dans quelques instants ou donnez un numéro de suivi."
# #                         )
# #                     source = "fallback"
# #                     llm_provider = None
# #                 else:
# #                     reply = (
# #                         "Je n'ai pas détecté de numéro de suivi FedEx exploitable dans votre message. "
# #                         "Merci d'indiquer un numéro valide (par exemple 12 ou 14 chiffres)."
# #                     )
# #                     source = "fallback"
# #                     llm_provider = None
# #
# #     reply = _safe_reply(reply)
# #
# #     if not deterministic:
# #         reply, validator_blocked, validator_reason = _apply_client_validator(
# #             reply,
# #             message=message,
# #             fedex_context_json=fedex_context_json,
# #             intent=intent_out,
# #             ui_language=ui_language,
# #             preferred_name=preferred_name,
# #             turn_plan=turn_plan,
# #         )
# #         if validator_blocked:
# #             source = "validator"
# #
# #     from app.services.client_reply_safety import repair_client_tracking_reply
# #
# #     reply = repair_client_tracking_reply(
# #         reply,
# #         message=message,
# #         tracking_number=tracking,
# #         fedex_error_code=tracking_error_code,
# #         fedex_context_json=fedex_context_json,
# #         ui_language=ui_language,
# #         preferred_name=preferred_name,
# #         conversation_history=conversation_history,
# #     )
# #
# #     if shipment_data:
# #         tr = TrackingRequest(
# #             user_id=user.id,
# #             session_id=session.id,
# #             tracking_number=shipment_data["tracking_number"],
# #             user_question=message,
# #             bot_response=reply,
# #             status=shipment_data.get("status"),
# #             current_location=shipment_data.get("current_location"),
# #             estimated_delivery=shipment_data.get("estimated_delivery"),
# #         )
# #         db.add(tr)
# #
# #     bot = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.bot.value,
# #         source=source,
# #         message_text=reply,
# #     )
# #     db.add(bot)
# #     title_source = message.strip() or ("Image FedEx" if has_image else message)
# #     _apply_session_title(
# #         session,
# #         title_source,
# #         bot_reply=reply,
# #         ui_language=ui_language,
# #         intent=intent_out,
# #         tracking_number=tracking,
# #         has_image=has_image,
# #     )
# #     db.commit()
# #     db.refresh(bot)
# #     result = _base_result(
# #         reply,
# #         session,
# #         shipment=shipment_for_client,
# #         source=source,
# #         intent=intent_out,
# #         tracking_number=tracking,
# #         llm_provider=llm_provider,
# #     )
# #     logger.info(
# #         "client_turn turn_type=%s tools_used=%s fedex_available=%s validator_blocked=%s validator_reason=%s",
# #         turn_plan.turn_type,
# #         [],
# #         bool(fedex_context_json),
# #         validator_blocked,
# #         validator_reason,
# #     )
# #     return result
# #
# #
# # def _process_conversational_turn(
# #     db: Session,
# #     user: User,
# #     message: str,
# #     session: ChatSession,
# #     *,
# #     ui_language: str | None = None,
# #     preferred_name: str | None = None,
# #     turn_plan: ClientTurnPlan | None = None,
# # ) -> dict[str, Any]:
# #     """Salutations et messages conversationnels — réponse locale, sans validateur."""
# #
# #     stored_message = pack_message_text(message, image_base64=None, image_mime_type=None)
# #     user_msg = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.user.value,
# #         source="user_input",
# #         message_text=stored_message,
# #     )
# #     db.add(user_msg)
# #     db.flush()
# #
# #     plan = turn_plan or plan_client_turn(message, tracking=None, tracking_source="none")
# #     if is_client_capabilities_message(message):
# #         reply = client_capabilities_reply(
# #             ui_language=ui_language,
# #             preferred_name=preferred_name or user.full_name,
# #         )
# #     else:
# #         reply = client_greeting_reply(
# #             ui_language=ui_language,
# #             preferred_name=preferred_name or user.full_name,
# #             message=message,
# #         )
# #
# #     bot = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.bot.value,
# #         source="conversational",
# #         message_text=reply,
# #     )
# #     db.add(bot)
# #     _apply_session_title(
# #         session,
# #         message.strip(),
# #         bot_reply=reply,
# #         ui_language=ui_language,
# #         intent=plan.intent_out,
# #     )
# #     db.commit()
# #     db.refresh(bot)
# #
# #     result = _base_result(
# #         reply,
# #         session,
# #         source="conversational",
# #         intent=plan.intent_out,
# #         tracking_number=None,
# #         llm_provider=None,
# #     )
# #     logger.info(
# #         "client_turn turn_type=%s tools_used=%s fedex_available=%s validator_blocked=%s validator_reason=%s",
# #         plan.turn_type,
# #         [],
# #         False,
# #         False,
# #         None,
# #     )
# #     return result
# #
# #
# # def _process_client_tracking_turn(
# #     db: Session,
# #     user: User,
# #     message: str,
# #     session: ChatSession,
# #     *,
# #     ui_language: str | None = None,
# #     preferred_name: str | None = None,
# #     turn_plan: ClientTurnPlan | None = None,
# # ) -> dict[str, Any]:
# #     """Suivi colis via boucle outils (3A) sans activer le mode agent UI."""
# #     from app.services.gpt.agent_runtime import run_gpt_agent_turn
# #     from app.services.gpt.orchestrator import SLUG_CLIENT
# #     from app.services.client_reply_safety import repair_client_tracking_reply
# #
# #     stored_message = pack_message_text(message, image_base64=None, image_mime_type=None)
# #     user_msg = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.user.value,
# #         source="tracking_tools",
# #         message_text=stored_message,
# #     )
# #     db.add(user_msg)
# #     db.flush()
# #
# #     conversation_history = build_conversation_history_for_llm(
# #         db,
# #         session_id=session.id,
# #         exclude_message_id=user_msg.id,
# #     )
# #     ship_ctx, conversation_history, server_instruction, plan = _resolve_client_tracking_context(
# #         db,
# #         user,
# #         session,
# #         message,
# #         conversation_history,
# #             turn_plan=turn_plan,
# #     )
# #     tn = ship_ctx.tracking
# #     fedex_context_json = ship_ctx.fedex_context_json
# #     tracking_error_code = ship_ctx.tracking_error_code
# #     tools_used: list[str] = []
# #     tool_payloads: list[dict[str, Any]] = []
# #     turn = None
# #     validator_blocked = False
# #     validator_reason: str | None = None
# #
# #     deterministic = _deterministic_shipment_reply_if_applicable(
# #         message,
# #         ship_ctx,
# #         ui_language=ui_language,
# #         preferred_name=preferred_name or user.full_name,
# #     )
# #     if deterministic:
# #         reply, turn_intent, intro_provider = deterministic
# #         source = "fedex_api"
# #         llm_provider = intro_provider
# #     else:
# #         turn = run_gpt_agent_turn(
# #             db,
# #             gpt_slug=SLUG_CLIENT,
# #             user=user,
# #             message=message,
# #             session_id=session.id,
# #             ui_language=ui_language,
# #             fedex_context=fedex_context_json,
# #             preferred_name=preferred_name or user.full_name,
# #             server_instruction=server_instruction,
# #             conversation_history=conversation_history or None,
# #             session_tracking_number=tn,
# #         )
# #         reply = _safe_reply(turn.reply)
# #         turn_intent = turn.intent
# #         llm_provider = turn.llm_provider
# #         tools_used = list(turn.tools_used or [])
# #         source = "gpt_agent"
# #         tool_payloads = [{"name": p.get("name"), "response": p.get("response")} for p in (turn.tool_payloads or [])]
# #
# #     if not deterministic:
# #         reply, validator_blocked, validator_reason = _apply_client_validator(
# #             reply,
# #             message=message,
# #             fedex_context_json=fedex_context_json,
# #             intent=turn_intent,
# #             ui_language=ui_language,
# #             preferred_name=preferred_name or user.full_name,
# #             tools_used=tools_used,
# #             tool_payloads=tool_payloads,
# #             turn_plan=plan,
# #         )
# #         if validator_blocked:
# #             source = "validator"
# #
# #     reply = repair_client_tracking_reply(
# #         reply,
# #         message=message,
# #         tracking_number=tn,
# #         fedex_error_code=tracking_error_code,
# #         fedex_context_json=fedex_context_json,
# #         ui_language=ui_language,
# #         preferred_name=preferred_name or user.full_name,
# #         conversation_history=conversation_history,
# #     )
# #
# #     if ship_ctx.shipment_data:
# #         shipment_data = ship_ctx.shipment_data
# #         tr = TrackingRequest(
# #             user_id=user.id,
# #             session_id=session.id,
# #             tracking_number=shipment_data["tracking_number"],
# #             user_question=message,
# #             bot_response=reply,
# #             status=shipment_data.get("status"),
# #             current_location=shipment_data.get("current_location"),
# #             estimated_delivery=shipment_data.get("estimated_delivery"),
# #         )
# #         db.add(tr)
# #
# #     bot = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.bot.value,
# #         source=source,
# #         message_text=reply,
# #     )
# #     db.add(bot)
# #     _apply_session_title(
# #         session,
# #         message.strip(),
# #         bot_reply=reply,
# #         ui_language=ui_language,
# #         intent=turn_intent,
# #         tracking_number=tn,
# #     )
# #     db.commit()
# #     db.refresh(bot)
# #
# #     result = _base_result(
# #         reply,
# #         session,
# #         shipment=ship_ctx.shipment_for_client,
# #         source=source,
# #         intent=turn_intent,
# #         tracking_number=tn,
# #         llm_provider=llm_provider,
# #     )
# #     result["agent_mode"] = False
# #     result["agent_phase"] = "completed"
# #     result["tools_used"] = tools_used
# #     if turn is not None:
# #         result["agent_steps"] = turn.agent_steps
# #         result["gpt_slug"] = turn.gpt_slug
# #         result["knowledge_hits"] = len(turn.knowledge_sources)
# #     else:
# #         result["agent_steps"] = []
# #     logger.info(
# #         "client_turn turn_type=%s tools_used=%s fedex_available=%s validator_blocked=%s validator_reason=%s",
# #         plan.turn_type,
# #         tools_used,
# #         bool(fedex_context_json),
# #         validator_blocked,
# #         validator_reason,
# #     )
# #     return result
# #
# #
# # def _fallback_simple_tracking_gpt_turn(
# #     db: Session,
# #     user: User,
# #     message: str,
# #     session: ChatSession,
# #     *,
# #     ui_language: str | None = None,
# #     user_msg_id: int | None = None,
# # ) -> dict[str, Any]:
# #     """Repli chat normal Ollama/Gemini quand l'agent GPT échoue sur un suivi simple."""
# #     from app.services.gpt.orchestrator import SLUG_CLIENT, run_gpt_turn
# #     from app.services.client_reply_safety import repair_client_tracking_reply
# #
# #     if user_msg_id is None:
# #         stored_message = pack_message_text(message, image_base64=None, image_mime_type=None)
# #         user_msg = ChatMessage(
# #             session_id=session.id,
# #             sender=MessageSender.user.value,
# #             source="user_input",
# #             message_text=stored_message,
# #         )
# #         db.add(user_msg)
# #         db.flush()
# #         user_msg_id = user_msg.id
# #
# #     conversation_history = build_conversation_history_for_llm(
# #         db,
# #         session_id=session.id,
# #         exclude_message_id=user_msg_id,
# #     )
# #
# #     ship_ctx, conversation_history, server_instruction, turn_plan = _resolve_client_tracking_context(
# #         db,
# #         user,
# #         session,
# #         message,
# #         conversation_history,
# #     )
# #     tn = ship_ctx.tracking
# #     fedex_context_json = ship_ctx.fedex_context_json
# #     tracking_error_code = ship_ctx.tracking_error_code
# #
# #     deterministic = _deterministic_shipment_reply_if_applicable(
# #         message,
# #         ship_ctx,
# #         ui_language=ui_language,
# #         preferred_name=user.full_name,
# #     )
# #     if deterministic:
# #         reply, intent_out, intro_provider = deterministic
# #         source = "fedex_api"
# #         turn_intent = intent_out
# #         llm_provider = intro_provider
# #     else:
# #         turn = run_gpt_turn(
# #             db,
# #             gpt_slug=SLUG_CLIENT,
# #             user_id=user.id,
# #             message=message,
# #             session_id=session.id,
# #             ui_language=ui_language,
# #             profile_language=user.preferred_language,
# #             fedex_context=fedex_context_json,
# #             preferred_name=user.full_name,
# #             conversation_history=conversation_history or None,
# #             exclude_message_id=user_msg_id,
# #             server_instruction=server_instruction,
# #         )
# #         reply = _safe_reply(turn.reply)
# #         source = turn.llm_provider if turn.llm_provider in {"gemini", "ollama"} else "llm"
# #         turn_intent = turn.intent
# #         llm_provider = turn.llm_provider
# #
# #     reply = _safe_reply(reply)
# #     if not deterministic:
# #         reply, _, _ = _apply_client_validator(
# #             reply,
# #             message=message,
# #             fedex_context_json=fedex_context_json,
# #             intent=turn_intent,
# #             ui_language=ui_language,
# #             preferred_name=user.full_name,
# #             turn_plan=turn_plan,
# #         )
# #     reply = repair_client_tracking_reply(
# #         reply,
# #         message=message,
# #         tracking_number=tn,
# #         fedex_error_code=tracking_error_code,
# #         fedex_context_json=fedex_context_json,
# #         ui_language=ui_language,
# #         preferred_name=user.full_name,
# #         conversation_history=conversation_history,
# #     )
# #     bot = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.bot.value,
# #         source=source,
# #         message_text=reply,
# #     )
# #     db.add(bot)
# #     _apply_session_title(
# #         session,
# #         message.strip(),
# #         bot_reply=reply,
# #         ui_language=ui_language,
# #         intent=turn_intent,
# #         tracking_number=tn,
# #     )
# #     db.commit()
# #     db.refresh(bot)
# #
# #     result = _base_result(
# #         reply,
# #         session,
# #         source=source,
# #         intent=turn_intent,
# #         tracking_number=tn,
# #         llm_provider=llm_provider,
# #     )
# #     result["agent_mode"] = False
# #     result["agent_phase"] = "completed"
# #     return result
# #
# #
# # def _process_agent_user_message(
# #     db: Session,
# #     user: User,
# #     message: str,
# #     session: ChatSession,
# #     *,
# #     ui_language: str | None = None,
# #     agent_flow_id: str | None = None,
# #     agent_answers: dict[str, str] | None = None,
# #     has_image: bool = False,
# # ) -> dict[str, Any]:
# #     settings = get_settings()
# #     gpt_user_msg_id: int | None = None
# #     if (
# #         settings.gpt_tools_enabled
# #         and settings.llm_enabled
# #         and not agent_flow_id
# #         and not agent_answers
# #         and not has_image
# #         and (message or "").strip()
# #     ):
# #         try:
# #             from app.services.gpt.agent_runtime import run_gpt_agent_turn
# #             from app.services.gpt.orchestrator import SLUG_CLIENT
# #
# #             stored_message = pack_message_text(message, image_base64=None, image_mime_type=None)
# #             user_msg = ChatMessage(
# #                 session_id=session.id,
# #                 sender=MessageSender.user.value,
# #                 source="agent_input",
# #                 message_text=stored_message,
# #             )
# #             db.add(user_msg)
# #             db.flush()
# #             gpt_user_msg_id = user_msg.id
# #
# #             conversation_history = build_conversation_history_for_llm(
# #                 db,
# #                 session_id=session.id,
# #                 exclude_message_id=gpt_user_msg_id,
# #             )
# #             ship_ctx, conversation_history, server_instruction, turn_plan = _resolve_client_tracking_context(
# #                 db,
# #                 user,
# #                 session,
# #                 message,
# #                 conversation_history,
# #             )
# #             tn = ship_ctx.tracking
# #             fedex_context_json = ship_ctx.fedex_context_json
# #             tracking_error_code = ship_ctx.tracking_error_code
# #             tools_used: list[str] = []
# #             tool_payloads: list[dict[str, Any]] = []
# #
# #             deterministic = _deterministic_shipment_reply_if_applicable(
# #                 message,
# #                 ship_ctx,
# #                 ui_language=ui_language,
# #                 preferred_name=user.full_name,
# #             )
# #             if deterministic:
# #                 reply, turn_intent, intro_provider = deterministic
# #                 llm_provider = intro_provider
# #                 turn = None
# #             else:
# #                 turn = run_gpt_agent_turn(
# #                     db,
# #                     gpt_slug=SLUG_CLIENT,
# #                     user=user,
# #                     message=message,
# #                     session_id=session.id,
# #                     ui_language=ui_language,
# #                     fedex_context=fedex_context_json,
# #                     preferred_name=user.full_name,
# #                     server_instruction=server_instruction,
# #                     conversation_history=conversation_history or None,
# #                     session_tracking_number=tn,
# #                 )
# #                 reply = _safe_reply(turn.reply)
# #                 turn_intent = turn.intent
# #                 llm_provider = turn.llm_provider
# #                 tools_used = list(turn.tools_used or [])
# #                 tool_payloads = [
# #                     {"name": p.get("name"), "response": p.get("response")}
# #                     for p in (turn.tool_payloads or [])
# #                 ]
# #
# #             from app.services.client_reply_safety import repair_client_tracking_reply
# #
# #             validator_blocked = False
# #             validator_reason: str | None = None
# #             bot_source = "fedex_api" if deterministic else "gpt_agent"
# #             if not deterministic:
# #                 reply, validator_blocked, validator_reason = _apply_client_validator(
# #                     reply,
# #                     message=message,
# #                     fedex_context_json=fedex_context_json,
# #                     intent=turn_intent,
# #                     ui_language=ui_language,
# #                     preferred_name=user.full_name,
# #                     tools_used=tools_used,
# #                     tool_payloads=tool_payloads,
# #                     turn_plan=turn_plan,
# #                 )
# #                 if validator_blocked:
# #                     bot_source = "validator"
# #
# #             reply = repair_client_tracking_reply(
# #                 reply,
# #                 message=message,
# #                 tracking_number=tn,
# #                 fedex_error_code=tracking_error_code,
# #                 fedex_context_json=fedex_context_json,
# #                 ui_language=ui_language,
# #                 preferred_name=user.full_name,
# #                 conversation_history=conversation_history,
# #             )
# #             bot = ChatMessage(
# #                 session_id=session.id,
# #                 sender=MessageSender.bot.value,
# #                 source=bot_source,
# #                 message_text=reply,
# #             )
# #             db.add(bot)
# #             if ship_ctx.shipment_data:
# #                 shipment_data = ship_ctx.shipment_data
# #                 tr = TrackingRequest(
# #                     user_id=user.id,
# #                     session_id=session.id,
# #                     tracking_number=shipment_data["tracking_number"],
# #                     user_question=message,
# #                     bot_response=reply,
# #                     status=shipment_data.get("status"),
# #                     current_location=shipment_data.get("current_location"),
# #                     estimated_delivery=shipment_data.get("estimated_delivery"),
# #                 )
# #                 db.add(tr)
# #             _apply_session_title(
# #                 session,
# #                 message.strip(),
# #                 bot_reply=reply,
# #                 ui_language=ui_language,
# #                 intent=turn_intent,
# #                 tracking_number=tn,
# #             )
# #             db.commit()
# #             db.refresh(bot)
# #
# #             result = _base_result(
# #                 reply,
# #                 session,
# #                 shipment=ship_ctx.shipment_for_client,
# #                 source=bot_source,
# #                 intent=turn_intent,
# #                 tracking_number=tn,
# #                 llm_provider=llm_provider,
# #             )
# #             result["agent_mode"] = True
# #             result["agent_phase"] = "completed"
# #             if turn is not None:
# #                 result["agent_steps"] = turn.agent_steps
# #                 result["tools_used"] = turn.tools_used
# #                 result["gpt_slug"] = turn.gpt_slug
# #                 result["knowledge_hits"] = len(turn.knowledge_sources)
# #                 if turn.export_download:
# #                     result["export_download"] = turn.export_download
# #             else:
# #                 result["agent_steps"] = []
# #                 result["tools_used"] = []
# #             logger.info(
# #                 "client_turn turn_type=%s tools_used=%s fedex_available=%s validator_blocked=%s validator_reason=%s",
# #                 turn_plan.turn_type,
# #                 result.get("tools_used") or [],
# #                 bool(fedex_context_json),
# #                 validator_blocked,
# #                 validator_reason,
# #             )
# #             return result
# #         except Exception:
# #             logger.exception("GPT agent client échoué — repli runtime agent classique")
# #             if is_simple_tracking_request(message):
# #                 return _fallback_simple_tracking_gpt_turn(
# #                     db,
# #                     user,
# #                     message,
# #                     session,
# #                     ui_language=ui_language,
# #                     user_msg_id=gpt_user_msg_id,
# #                 )
# #
# #     if gpt_user_msg_id is None:
# #         stored_message = pack_message_text(
# #             message or ("[Réponses agent]" if agent_answers else ""),
# #             image_base64=None,
# #             image_mime_type=None,
# #         )
# #         user_msg = ChatMessage(
# #             session_id=session.id,
# #             sender=MessageSender.user.value,
# #             source="agent_input" if agent_answers else "user_input",
# #             message_text=stored_message,
# #         )
# #         db.add(user_msg)
# #         db.flush()
# #         classic_user_msg_id = user_msg.id
# #     else:
# #         classic_user_msg_id = gpt_user_msg_id
# #
# #     conversation_history = build_conversation_history_for_llm(
# #         db,
# #         session_id=session.id,
# #         exclude_message_id=classic_user_msg_id,
# #     )
# #
# #     agent_result = process_agent_message(
# #         db,
# #         user=user,
# #         message=message,
# #         session_id=session.id,
# #         agent_answers=agent_answers,
# #         agent_flow_id=agent_flow_id,
# #         ui_language=ui_language or "fr",
# #         conversation_history=conversation_history,
# #     )
# #
# #     reply = _safe_reply(agent_result.get("reply") or "")
# #     from app.services.client_reply_safety import repair_client_tracking_reply
# #
# #     reply = repair_client_tracking_reply(
# #         reply,
# #         message=message,
# #         tracking_number=agent_result.get("tracking_number"),
# #         fedex_error_code=agent_result.get("tracking_error_code"),
# #         fedex_context_json=agent_result.get("fedex_context_json"),
# #         ui_language=ui_language or "fr",
# #         preferred_name=user.full_name,
# #         conversation_history=conversation_history,
# #     )
# #     bot = ChatMessage(
# #         session_id=session.id,
# #         sender=MessageSender.bot.value,
# #         source=agent_result.get("source", "agent"),
# #         message_text=reply,
# #     )
# #     db.add(bot)
# #
# #     intent_out = agent_result.get("intent") or "agent"
# #     tracking = agent_result.get("tracking_number")
# #     title_source = message.strip() or ("Mode Agent" if not agent_answers else "Réponses agent")
# #     _apply_session_title(
# #         session,
# #         title_source,
# #         bot_reply=reply,
# #         ui_language=ui_language,
# #         intent=intent_out,
# #         tracking_number=tracking,
# #         has_image=has_image,
# #     )
# #     db.commit()
# #     db.refresh(bot)
# #
# #     result = _base_result(
# #         reply,
# #         session,
# #         shipment=agent_result.get("shipment"),
# #         source=agent_result.get("source", "agent"),
# #         intent=intent_out,
# #         tracking_number=tracking,
# #         llm_provider=agent_result.get("llm_provider"),
# #     )
# #     result["agent_mode"] = agent_result.get("agent_mode", True)
# #     result["agent_phase"] = agent_result.get("agent_phase")
# #     result["agent_questionnaire"] = agent_result.get("agent_questionnaire")
# #     result["agent_steps"] = agent_result.get("agent_steps") or []
# #     result["agent_reasoning"] = agent_result.get("agent_reasoning")
# #     result["export_download"] = agent_result.get("export_download")
# #     return result
# # =============================================================================
# # ACTIVE — Phase 0 stub
# # =============================================================================
# """Chat client — délégation au noyau client_agent v2."""
#
# from __future__ import annotations
#
# import logging
# from typing import Any
#
# from sqlalchemy import func
# from sqlalchemy.orm import Session
#
# from app.models.chat_message import ChatMessage, MessageSender
# from app.models.chat_session import ChatSession
# from app.models.user import User
# from app.core.config import get_settings
# from app.services.client_agent.kernel import run_turn
# from app.services.llm.session_title import heuristic_session_title, should_auto_rename
# from app.services.message_attachment import normalize_image_mime, pack_message_text
# from app.services.prompt_guard_service import assess_user_message, must_block_preferences
# from app.services.llm.prompts import prompt_injection_refusal
# from app.services.tracking_record_service import persist_tracking_request, shipment_data_from_turn
#
# logger = logging.getLogger(__name__)
#
#
# def _base_result(
#     reply: str,
#     session: ChatSession,
#     *,
#     shipment: dict[str, Any] | None = None,
#     source: str,
#     intent: str,
#     tracking_number: str | None,
#     llm_provider: str | None,
# ) -> dict[str, Any]:
#     return {
#         "reply": reply,
#         "session_id": session.id,
#         "session_title": session.title,
#         "shipment": shipment,
#         "source": source,
#         "intent": intent,
#         "tracking_number": tracking_number,
#         "llm_provider": llm_provider,
#     }
#
#
# def process_user_message(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     response_preferences: str | None = None,
#     preferred_name: str | None = None,
#     ui_language: str | None = None,
#     image_base64: str | None = None,
#     image_mime_type: str | None = None,
#     agent_mode: bool = False,
#     agent_flow_id: str | None = None,
#     agent_answers: dict[str, str] | None = None,
# ) -> dict[str, Any]:
#     """Traite un message utilisateur client. agent_mode est ignoré (assistant unique)."""
#     settings = get_settings()
#     probe_text = (message or "").strip()
#     if settings.prompt_guard_enabled and probe_text and not (image_base64 or "").strip():
#         risk = assess_user_message(probe_text)
#         if must_block_preferences(risk):
#             lang = (ui_language or user.preferred_language or "fr").lower()
#             refusal = prompt_injection_refusal(lang)
#             return {
#                 "reply": refusal,
#                 "session_id": session.id,
#                 "session_title": session.title,
#                 "source": "security",
#                 "intent": "security_blocked",
#                 "tracking_number": None,
#                 "llm_provider": None,
#                 "shipment": None,
#                 "agent_mode": False,
#             }
#
#     try:
#         b64 = (image_base64 or "").strip() or None
#         mime = normalize_image_mime(image_mime_type) if b64 else None
#         stored_message = pack_message_text(message, image_base64=b64, image_mime_type=mime)
#
#         user_msg = ChatMessage(
#             session_id=session.id,
#             sender=MessageSender.user.value,
#             source="user_input",
#             message_text=stored_message,
#         )
#         db.add(user_msg)
#         db.flush()
#
#         turn = run_turn(
#             db,
#             user,
#             message,
#             session,
#             response_preferences=response_preferences,
#             preferred_name=preferred_name,
#             ui_language=ui_language,
#             image_base64=image_base64,
#             image_mime_type=image_mime_type,
#             agent_mode=agent_mode,
#             agent_flow_id=agent_flow_id,
#             agent_answers=agent_answers,
#             current_user_message_id=user_msg.id,
#         )
#
#         bot = ChatMessage(
#             session_id=session.id,
#             sender=MessageSender.bot.value,
#             source=turn.source,
#             message_text=turn.reply,
#         )
#         db.add(bot)
#
#         if turn.tracking_number and turn.intent == "client_agent":
#             shipment_data = shipment_data_from_turn(turn.shipment, tracking_number=turn.tracking_number)
#             if shipment_data:
#                 try:
#                     persist_tracking_request(
#                         db,
#                         user_id=user.id,
#                         session_id=session.id,
#                         tracking_number=turn.tracking_number,
#                         user_question=message,
#                         bot_response=turn.reply,
#                         shipment_data=shipment_data,
#                     )
#                 except Exception:
#                     logger.warning(
#                         "persist_tracking_request fallback failed for %s",
#                         turn.tracking_number,
#                         exc_info=True,
#                     )
#
#         title_source = message.strip() or ("Image FedEx" if b64 else message)
#         if should_auto_rename(session.title):
#             session.title = heuristic_session_title(
#                 title_source,
#                 ui_language=ui_language,
#                 intent=turn.intent,
#                 tracking_number=turn.tracking_number,
#             )
#         session.updated_at = func.now()
#         db.commit()
#         db.refresh(bot)
#
#         result = _base_result(
#             turn.reply,
#             session,
#             shipment=turn.shipment,
#             source=turn.source,
#             intent=turn.intent,
#             tracking_number=turn.tracking_number,
#             llm_provider=turn.llm_provider,
#         )
#         if turn.agent_mode is not None:
#             result["agent_mode"] = turn.agent_mode
#         else:
#             result["agent_mode"] = False
#         if turn.export_download:
#             result["export_download"] = turn.export_download
#         if turn.tools_used:
#             result["tools_used"] = turn.tools_used
#         if turn.agent_mode is not None and turn.agent_mode:
#             result["agent_mode"] = True
#         return result
#     except Exception:
#         logger.exception("client_agent kernel stub failure")
#         db.rollback()
#         return {
#             "reply": (
#                 "Désolé, une erreur technique est survenue. "
#                 "L'assistant est en cours de reconstruction — réessayez dans un instant."
#             ),
#             "session_id": session.id,
#             "session_title": session.title,
#             "source": "fallback",
#             "intent": "error",
#             "tracking_number": None,
#             "llm_provider": None,
#             "shipment": None,
#             "agent_mode": False,
#         }
# =============================================================================
# ACTIVE — Phase 1 stub
# =============================================================================
"""Chat client — Phase 1 Ollama minimal (prompt court, sans client_agent)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.core.config import get_settings
from app.services.llm.providers import LlmProviderError, call_ollama_simple
from app.services.llm.session_title import heuristic_session_title, should_auto_rename
from app.services.message_attachment import normalize_image_mime, pack_message_text
from app.services.prompt_guard_service import assess_user_message, must_block_preferences
from app.services.llm.prompts import prompt_injection_refusal

logger = logging.getLogger(__name__)

_OLLAMA_FALLBACK = {
    "fr": "Désolé, l'assistant met trop de temps à répondre. Réessayez dans un instant.",
    "en": "Sorry, the assistant is taking too long. Please try again shortly.",
}

_IMAGE_NOT_SUPPORTED = {
    "fr": "L'envoi d'images n'est pas encore disponible. Décrivez votre demande en texte.",
    "en": "Image upload is not available yet. Please describe your request in text.",
}

_LLM_DISABLED = {
    "fr": "L'assistant IA est temporairement désactivé. Réessayez plus tard.",
    "en": "The AI assistant is temporarily disabled. Please try again later.",
}


def _lang_code(ui_language: str | None, user: User) -> str:
    return (ui_language or user.preferred_language or "fr").lower()[:2]


def _ollama_fallback_reply(ui_language: str | None, user: User) -> str:
    return _OLLAMA_FALLBACK.get(_lang_code(ui_language, user), _OLLAMA_FALLBACK["fr"])


def _image_not_supported_reply(ui_language: str | None, user: User) -> str:
    return _IMAGE_NOT_SUPPORTED.get(_lang_code(ui_language, user), _IMAGE_NOT_SUPPORTED["fr"])


def _llm_disabled_reply(ui_language: str | None, user: User) -> str:
    return _LLM_DISABLED.get(_lang_code(ui_language, user), _LLM_DISABLED["fr"])


def _base_result(
    reply: str,
    session: ChatSession,
    *,
    shipment: dict[str, Any] | None = None,
    source: str,
    intent: str,
    tracking_number: str | None,
    llm_provider: str | None,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "session_id": session.id,
        "session_title": session.title,
        "shipment": shipment,
        "source": source,
        "intent": intent,
        "tracking_number": tracking_number,
        "llm_provider": llm_provider,
    }


def process_user_message(
    db: Session,
    user: User,
    message: str,
    session: ChatSession,
    response_preferences: str | None = None,
    preferred_name: str | None = None,
    ui_language: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    agent_mode: bool = False,
    agent_flow_id: str | None = None,
    agent_answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Traite un message utilisateur client — Phase 1 Ollama minimal."""
    settings = get_settings()
    probe_text = (message or "").strip()
    if settings.prompt_guard_enabled and probe_text and not (image_base64 or "").strip():
        risk = assess_user_message(probe_text)
        if must_block_preferences(risk):
            lang = (ui_language or user.preferred_language or "fr").lower()
            refusal = prompt_injection_refusal(lang)
            return {
                "reply": refusal,
                "session_id": session.id,
                "session_title": session.title,
                "source": "security",
                "intent": "security_blocked",
                "tracking_number": None,
                "llm_provider": None,
                "shipment": None,
                "agent_mode": False,
            }

    try:
        b64 = (image_base64 or "").strip() or None
        mime = normalize_image_mime(image_mime_type) if b64 else None
        stored_message = pack_message_text(message, image_base64=b64, image_mime_type=mime)

        user_msg = ChatMessage(
            session_id=session.id,
            sender=MessageSender.user.value,
            source="user_input",
            message_text=stored_message,
        )
        db.add(user_msg)
        db.flush()

        if b64:
            reply = _image_not_supported_reply(ui_language, user)
            source, intent, llm_provider = "phase1", "image_not_supported", None
        elif not settings.llm_enabled:
            reply = _llm_disabled_reply(ui_language, user)
            source, intent, llm_provider = "phase1", "llm_disabled", None
        else:
            try:
                reply = call_ollama_simple(
                    message.strip() or "Bonjour",
                    ui_language=ui_language,
                )
                source, intent, llm_provider = "ollama", "general", "ollama"
            except LlmProviderError:
                logger.warning("Phase 1 call_ollama failed", exc_info=True)
                reply = _ollama_fallback_reply(ui_language, user)
                source, intent, llm_provider = "fallback", "ollama_error", None

        bot = ChatMessage(
            session_id=session.id,
            sender=MessageSender.bot.value,
            source=source,
            message_text=reply,
        )
        db.add(bot)

        title_source = message.strip() or ("Image FedEx" if b64 else message)
        if should_auto_rename(session.title):
            session.title = heuristic_session_title(
                title_source,
                ui_language=ui_language,
                intent=intent,
                tracking_number=None,
            )
        session.updated_at = func.now()
        db.commit()
        db.refresh(bot)

        result = _base_result(
            reply,
            session,
            source=source,
            intent=intent,
            tracking_number=None,
            llm_provider=llm_provider,
        )
        result["agent_mode"] = False
        return result
    except Exception:
        logger.exception("chatbot Phase 1 failure")
        db.rollback()
        return {
            "reply": _ollama_fallback_reply(ui_language, user),
            "session_id": session.id,
            "session_title": session.title,
            "source": "fallback",
            "intent": "error",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "agent_mode": False,
        }
