# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Boucle outils Ollama — assistant client Phase 3 (LLM orchestrateur)."""
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
#     message_unrelated_to_shipment,
# )
# from app.services.client_agent.export_routing import is_pdf_export_intent, tracking_pdf_preset
# from app.services.client_agent.capabilities import (
#     CAP_EXCEL,
#     CAP_FEDEX,
#     CAP_PDF,
#     has_client_capability,
#     is_phase1_chat_only,
# )
# from app.services.client_agent.facts import FedExTurnFacts, fetch_shipment_turn
# from app.services.client_agent.history import load_ollama_history
# from app.services.client_agent.ollama_bridge import chat_turn
# from app.services.client_agent.routing import (
#     is_shipment_question_without_tracking,
#     missing_tracking_prompt,
#     should_use_conversational_light_path,
# )
# from app.services.client_agent.types import ClientTurnResult
# from app.services.gpt.agent_runtime import AGENT_TOOLS_SYSTEM_APPEND, _run_tool_agent_loop
# from app.services.gpt.knowledge_service import format_knowledge_block, retrieve_knowledge
# from app.services.gpt.memory_service import build_memory_context, format_memory_block
# from app.services.gpt.orchestrator import SLUG_CLIENT, load_gpt_by_slug, run_gpt_turn
# from app.services.gpt.prompt_composer import build_gpt_user_payload
# from app.services.gpt.prompts import client_gpt_system_for_lang, client_gpt_system_phase1_for_lang
# from app.services.gpt.tool_executor import execute_tool
# from app.services.gpt.tool_registry import gemini_tool_declarations, list_tools_for_gpt, ollama_tool_declarations
# from app.services.client_reply_safety import (
#     deterministic_tracking_reply,
#     fedex_deterministic_reply_if_available,
#     is_fedex_external_redirect_boilerplate,
#     is_generic_tracking_boilerplate,
#     repair_client_tracking_reply,
#     repair_phase1_client_reply,
# )
# from app.services.gpt.tool_synthesis import (
#     all_tools_failed,
#     synthesize_client_tool_turn,
# )
# from app.services.gpt.tool_types import ToolCall, ToolExecutionContext
# from app.services.llm.fedex_context import client_tracking_server_instruction
# from app.services.llm.providers import resolve_ui_language
# from app.services.tracking_presenter import shipment_summary
# from app.services.tracking_record_service import ensure_tracking_in_db_for_export, persist_tracking_request
#
# logger = logging.getLogger(__name__)
#
# _FALLBACK_FR = (
#     "Désolé, je ne peux pas traiter votre demande pour le moment. "
#     "Réessayez dans un instant ou vérifiez qu'Ollama est lancé."
# )
# _FALLBACK_EN = (
#     "Sorry, I cannot process your request right now. "
#     "Please try again shortly or check that Ollama is running."
# )
#
#
# def _reply_text(value: Any) -> str:
#     return value.strip() if isinstance(value, str) else ""
#
#
# def _tracking_from_tool_payloads(tool_payloads: list[dict[str, Any]]) -> str | None:
#     for item in tool_payloads:
#         if item.get("name") != "fedex_track_package":
#             continue
#         payload = item.get("response") if isinstance(item.get("response"), dict) else {}
#         if payload.get("status") != "ok":
#             continue
#         tn = str(payload.get("tracking_number") or "").strip()
#         if tn:
#             return tn
#     return None
#
#
# def _pdf_failure_reply(
#     *,
#     lang: str,
#     message: str,
#     resolved_tracking: str | None,
#     track_error: str | None = None,
# ) -> str:
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     tn = (resolved_tracking or "").strip() or extract_tracking_number(message or "")
#     if not tn:
#         if lang == "en":
#             return (
#                 "To generate the PDF, I need your FedEx tracking number. "
#                 "Please share it (12 to 15 digits)."
#             )
#         return (
#             "Pour générer le PDF, j'ai besoin de votre numéro de suivi FedEx. "
#             "Merci de me le communiquer (12 à 15 chiffres)."
#         )
#
#     if track_error == "not_found":
#         if lang == "en":
#             return (
#                 f"I could not find shipment {tn} in the FedEx system. "
#                 "Please check the number and try again."
#             )
#         return (
#             f"Je n'ai pas trouvé le colis {tn} dans le système FedEx. "
#             "Vérifiez le numéro et réessayez."
#         )
#
#     if lang == "en":
#         return (
#             f"I could not prepare the PDF for tracking number {tn}. "
#             "Please verify the number or try again in a moment."
#         )
#     return (
#         f"Je n'ai pas pu préparer le PDF pour le numéro {tn}. "
#         "Vérifiez le numéro ou réessayez dans un instant."
#     )
#
#
# def _apply_pdf_export_safety_net(
#     *,
#     db: Session,
#     message: str,
#     tool_ctx: ToolExecutionContext,
#     tool_payloads: list[dict[str, Any]],
#     side_effects: dict[str, Any],
#     resolved_tracking: str | None,
# ) -> None:
#     """Garantit export_download si PDF demandé — track, persist, export."""
#     if not is_pdf_export_intent(message):
#         return
#     if side_effects.get("export_download"):
#         return
#
#     from app.services.gpt.tool_client_handlers import _handle_client_export_tracking_pdf
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     tn = (resolved_tracking or "").strip() or extract_tracking_number(message or "")
#     if not tn:
#         tn = _tracking_from_tool_payloads(tool_payloads)
#     if not tn:
#         return
#
#     ok, err_code = ensure_tracking_in_db_for_export(
#         db,
#         user_id=tool_ctx.user_id,
#         session_id=tool_ctx.session_id,
#         tracking_number=tn,
#         user_message=message,
#     )
#     if not ok:
#         side_effects["pdf_track_error"] = err_code or "track_failed"
#         return
#
#     preset = tracking_pdf_preset(message)
#     result = _handle_client_export_tracking_pdf(
#         tool_ctx,
#         {
#             "scope": "session",
#             "preset": preset,
#             "tracking_number": tn,
#         },
#     )
#     if not result.success:
#         if result.data.get("error_code") == "no_parcels":
#             side_effects["pdf_track_error"] = "no_parcels"
#         return
#
#     export_spec = result.data.get("export_download")
#     if not export_spec:
#         return
#
#     if isinstance(export_spec, dict) and not export_spec.get("format"):
#         export_spec = {**export_spec, "format": "pdf"}
#
#     side_effects["export_download"] = export_spec
#     tool_payloads.append(
#         {
#             "name": "client_export_tracking_pdf",
#             "response": result.to_function_response(),
#         }
#     )
#     logger.info(
#         "client_tool_bridge pdf safety net applied tn=%s preset=%s",
#         tn[:4] + "…",
#         preset,
#     )
#
#
# def _prefetch_fedex_context(
#     db: Session,
#     user_id: int,
#     message: str,
#     *,
#     resolved_tracking: str | None,
#     tracking_source: str | None,
# ) -> FedExTurnFacts | None:
#     """Charge les données FedEx en coulisses pour injection FEDEX_DATA au LLM."""
#     tn = (resolved_tracking or "").strip()
#     if not tn:
#         return None
#     try:
#         return fetch_shipment_turn(
#             db,
#             user_id,
#             tn,
#             message,
#             tracking_source=tracking_source or "session",
#         )
#     except Exception:
#         logger.warning("fedex prefetch failed for %s", tn[:4] + "…", exc_info=True)
#         return None
#
#
# def _apply_prefetch_fedex_synthesis(
#     *,
#     reply: str,
#     message: str,
#     tools_used: list[str],
#     fedex_facts: FedExTurnFacts | None,
#     resolved_tracking: str | None,
#     lang: str,
#     preferred_name: str | None,
# ) -> str:
#     """Synthèse depuis FEDEX_DATA prefetch si le LLM n'a pas appelé d'outil."""
#     if tools_used:
#         return reply
#     if is_pdf_export_intent(message):
#         return reply
#     if not resolved_tracking or not fedex_facts or not fedex_facts.fedex_context_json:
#         return reply
#     bad_reply = (
#         is_generic_tracking_boilerplate(
#             reply,
#             tracking_number=resolved_tracking,
#             message=message,
#         )
#         or is_fedex_external_redirect_boilerplate(
#             reply,
#             tracking_number=resolved_tracking,
#             message=message,
#             fedex_error_code=fedex_facts.error_code,
#         )
#     )
#     if not bad_reply:
#         return reply
#     deterministic = deterministic_tracking_reply(
#         message=message,
#         tracking_number=resolved_tracking,
#         shipment_data=fedex_facts.shipment_data if fedex_facts else None,
#         fedex_context_json=fedex_facts.fedex_context_json if fedex_facts else None,
#         fedex_error_code=fedex_facts.error_code if fedex_facts else None,
#         preferred_name=preferred_name,
#         ui_language=lang,
#         enrich_ctx=fedex_facts.enrich_ctx if fedex_facts else None,
#     )
#     if deterministic and deterministic.strip():
#         return deterministic.strip()
#     return reply
#
#
# def _build_shipment_payload(
#     fedex_facts: FedExTurnFacts | None,
#     tracking_number: str | None,
# ) -> dict[str, Any] | None:
#     if not fedex_facts or not fedex_facts.shipment_data or not tracking_number:
#         return None
#     from app.services.chat_shipment_reply import should_attach_shipment_card, shipment_card_display_flags
#
#     enrich = fedex_facts.enrich_ctx or {}
#     if not should_attach_shipment_card(
#         intent=fedex_facts.intent,
#         tracking_source=fedex_facts.tracking_source,
#         pod_available=enrich.get("pod_available", False),
#     ):
#         return None
#     flags = shipment_card_display_flags(fedex_facts.intent)
#     return shipment_summary(
#         fedex_facts.shipment_data,
#         extras=enrich,
#         show_tracking_map=bool(flags.get("show_tracking_map")),
#         show_timeline=bool(flags.get("show_timeline")),
#         max_timeline_events=int(flags.get("max_timeline_events") or 0),
#     )
#
#
# def _filter_tools_by_capabilities(tools: list) -> list:
#     """Filtre les outils selon CLIENT_AGENT_CAPABILITIES."""
#     if is_phase1_chat_only():
#         return []
#     allowed: set[str] = set()
#     if has_client_capability(CAP_FEDEX):
#         allowed.update(
#             {
#                 "fedex_track_package",
#                 "find_fedex_location",
#                 "client_watch_shipment",
#                 "client_open_support_ticket",
#             }
#         )
#     if has_client_capability(CAP_PDF):
#         allowed.update({"client_export_tracking_pdf", "client_generate_text_pdf"})
#     if has_client_capability(CAP_EXCEL):
#         allowed.add("client_export_tracking_excel")
#     if not allowed:
#         return []
#     return [t for t in tools if t.name in allowed]
#
#
# def finalize_phase1_reply(
#     *,
#     reply: str,
#     message: str,
#     preferred_name: str | None,
#     lang: str,
# ) -> str:
#     """Garde-fou anti-boilerplate Phase 1 — pas de FedEx."""
#     reply = _reply_text(reply)
#     if not reply:
#         return reply
#     return repair_phase1_client_reply(
#         reply,
#         message=message,
#         preferred_name=preferred_name,
#         ui_language=lang,
#     )
#
#
# def finalize_client_tracking_turn(
#     *,
#     reply: str,
#     message: str,
#     resolved_tracking: str | None,
#     fedex_facts: FedExTurnFacts | None,
#     fedex_context: str | None,
#     tools_used: list[str] | None,
#     lang: str,
#     preferred_name: str | None,
#     conversation_history: str | None,
#     db: Session,
#     user: User,
#     session: ChatSession,
# ) -> tuple[str, str | None, dict[str, Any] | None]:
#     """Synthèse prefetch, repair suivi et persistance — tous chemins de sortie."""
#     tracking_number = (resolved_tracking or "").strip() or None
#     shipment_payload = _build_shipment_payload(fedex_facts, tracking_number)
#
#     reply = _reply_text(reply)
#     reply = _apply_prefetch_fedex_synthesis(
#         reply=reply,
#         message=message,
#         tools_used=tools_used or [],
#         fedex_facts=fedex_facts,
#         resolved_tracking=resolved_tracking,
#         lang=lang,
#         preferred_name=preferred_name,
#     )
#
#     if resolved_tracking:
#         reply = repair_client_tracking_reply(
#             reply,
#             message=message,
#             tracking_number=tracking_number or resolved_tracking,
#             fedex_error_code=fedex_facts.error_code if fedex_facts else None,
#             fedex_context_json=fedex_context,
#             ui_language=lang,
#             preferred_name=preferred_name,
#             conversation_history=conversation_history,
#             shipment_data=fedex_facts.shipment_data if fedex_facts else None,
#             enrich_ctx=fedex_facts.enrich_ctx if fedex_facts else None,
#         )
#
#     if tracking_number and fedex_facts and fedex_facts.shipment_data and (reply or "").strip():
#         try:
#             persist_tracking_request(
#                 db,
#                 user_id=user.id,
#                 session_id=session.id,
#                 tracking_number=tracking_number,
#                 user_question=message,
#                 bot_response=reply.strip(),
#                 shipment_data=fedex_facts.shipment_data,
#             )
#         except Exception:
#             logger.warning("persist_tracking_request finalize failed", exc_info=True)
#
#     return reply.strip(), tracking_number, shipment_payload
#
#
# def _client_turn_from_reply(
#     *,
#     reply: str,
#     message: str,
#     resolved_tracking: str | None,
#     fedex_facts: FedExTurnFacts | None,
#     fedex_context: str | None,
#     tools_used: list[str] | None,
#     lang: str,
#     preferred_name: str | None,
#     conversation_history: str | None,
#     db: Session,
#     user: User,
#     session: ChatSession,
#     llm_provider: str | None,
#     export_download: dict[str, Any] | None = None,
# ) -> ClientTurnResult:
#     if is_phase1_chat_only():
#         reply = finalize_phase1_reply(
#             reply=reply,
#             message=message,
#             preferred_name=preferred_name,
#             lang=lang,
#         )
#         if not reply:
#             reply = _FALLBACK_EN if lang == "en" else _FALLBACK_FR
#             llm_provider = llm_provider or "fallback"
#         return ClientTurnResult(
#             reply=reply,
#             source="llm",
#             intent="client_agent",
#             llm_provider=llm_provider,
#             export_download=export_download,
#             agent_mode=True,
#         )
#
#     reply, tracking_number, shipment_payload = finalize_client_tracking_turn(
#         reply=reply,
#         message=message,
#         resolved_tracking=resolved_tracking,
#         fedex_facts=fedex_facts,
#         fedex_context=fedex_context,
#         tools_used=tools_used,
#         lang=lang,
#         preferred_name=preferred_name,
#         conversation_history=conversation_history,
#         db=db,
#         user=user,
#         session=session,
#     )
#     if not reply:
#         reply = _FALLBACK_EN if lang == "en" else _FALLBACK_FR
#         llm_provider = llm_provider or "fallback"
#     return ClientTurnResult(
#         reply=reply,
#         source="llm",
#         intent="client_agent",
#         llm_provider=llm_provider,
#         tracking_number=tracking_number,
#         shipment=shipment_payload,
#         export_download=export_download,
#         tools_used=tools_used or None,
#         agent_mode=True,
#     )
#
#
# def _llm_fallback_turn(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     *,
#     lang: str,
#     ui_language: str | None,
#     preferred_name: str | None,
#     response_preferences: str | None,
#     conversation_history: str | None,
#     exclude_id: int | None,
#     fedex_context: str | None,
#     resolved_tracking: str | None,
# ) -> ClientTurnResult | None:
#     """Repli RAG + mémoire sans boucle outils (Gemini uniquement si clé configurée)."""
#     from app.services.llm.providers import gemini_api_key_usable
#
#     if not gemini_api_key_usable():
#         return None
#     try:
#         turn = run_gpt_turn(
#             db,
#             gpt_slug=SLUG_CLIENT,
#             user_id=user.id,
#             message=message,
#             session_id=session.id,
#             ui_language=ui_language,
#             profile_language=user.preferred_language,
#             fedex_context=fedex_context,
#             response_preferences=response_preferences,
#             preferred_name=preferred_name or getattr(user, "full_name", None),
#             conversation_history=conversation_history,
#             exclude_message_id=exclude_id,
#         )
#         if not (turn.reply or "").strip():
#             return None
#         return ClientTurnResult(
#             reply=turn.reply.strip(),
#             source="llm",
#             intent="client_agent",
#             tracking_number=resolved_tracking,
#             llm_provider=turn.llm_provider,
#         )
#     except Exception:
#         logger.warning("client_tool_bridge run_gpt_turn fallback failed", exc_info=True)
#         return None
#
#
# def _resolve_tool_loop_failure(
#     *,
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     lang: str,
#     ui_language: str | None,
#     preferred_name: str | None,
#     response_preferences: str | None,
#     conversation_history: str | None,
#     exclude_id: int | None,
#     fedex_context: str | None,
#     resolved_tracking: str | None,
#     fedex_facts: FedExTurnFacts | None,
#     has_image: bool,
# ) -> ClientTurnResult:
#     """Repli après échec boucle outils — prefetch FedEx d'abord, puis LLM léger."""
#     det = fedex_deterministic_reply_if_available(
#         message=message,
#         resolved_tracking=resolved_tracking,
#         fedex_facts=fedex_facts,
#         fedex_context_json=fedex_context,
#         preferred_name=preferred_name,
#         ui_language=lang,
#         reason="ollama_timeout",
#     )
#     if det:
#         return _client_turn_from_reply(
#             reply=det,
#             message=message,
#             resolved_tracking=resolved_tracking,
#             fedex_facts=fedex_facts,
#             fedex_context=fedex_context,
#             tools_used=[],
#             lang=lang,
#             preferred_name=preferred_name,
#             conversation_history=conversation_history,
#             db=db,
#             user=user,
#             session=session,
#             llm_provider="deterministic",
#         )
#
#     fallback = _llm_fallback_turn(
#         db,
#         user,
#         message,
#         session,
#         lang=lang,
#         ui_language=ui_language,
#         preferred_name=preferred_name,
#         response_preferences=response_preferences,
#         conversation_history=conversation_history,
#         exclude_id=exclude_id,
#         fedex_context=fedex_context,
#         resolved_tracking=resolved_tracking,
#     )
#     if fallback is not None:
#         return _client_turn_from_reply(
#             reply=fallback.reply,
#             message=message,
#             resolved_tracking=resolved_tracking,
#             fedex_facts=fedex_facts,
#             fedex_context=fedex_context,
#             tools_used=[],
#             lang=lang,
#             preferred_name=preferred_name,
#             conversation_history=conversation_history,
#             db=db,
#             user=user,
#             session=session,
#             llm_provider=fallback.llm_provider,
#         )
#
#     try:
#         history = load_ollama_history(
#             db,
#             session.id,
#             exclude_message_id=exclude_id,
#         )
#         fallback_reply, fallback_source = chat_turn(
#             user_message=message or "(message vide)",
#             history_messages=history,
#             ui_language=lang,
#             has_image=has_image,
#         )
#         if (fallback_reply or "").strip() and fallback_source != "fallback":
#             return _client_turn_from_reply(
#                 reply=fallback_reply.strip(),
#                 message=message,
#                 resolved_tracking=resolved_tracking,
#                 fedex_facts=fedex_facts,
#                 fedex_context=fedex_context,
#                 tools_used=[],
#                 lang=lang,
#                 preferred_name=preferred_name,
#                 conversation_history=conversation_history,
#                 db=db,
#                 user=user,
#                 session=session,
#                 llm_provider="ollama" if fallback_source == "ollama" else None,
#             )
#     except Exception:
#         logger.exception("client_tool_bridge ollama fallback failed")
#
#     return ClientTurnResult(
#         reply=_FALLBACK_EN if lang == "en" else _FALLBACK_FR,
#         source="fallback",
#         intent="client_agent",
#     )
#
#
# def _run_conversational_light_turn(
#     db: Session,
#     *,
#     user: User,
#     message: str,
#     session: ChatSession,
#     lang: str,
#     ui_language: str | None,
#     preferred_name: str | None,
#     exclude_id: int | None,
#     has_image: bool,
# ) -> ClientTurnResult:
#     """Conversation légère — Ollama /api/chat sans RAG, outils ni prefetch FedEx."""
#     logger.info("client_tool_bridge conversational light path")
#     history = load_ollama_history(
#         db,
#         session.id,
#         exclude_message_id=exclude_id,
#     )
#     reply, source = chat_turn(
#         user_message=message or "(message vide)",
#         history_messages=history,
#         ui_language=lang,
#         has_image=has_image,
#         system_instruction=client_gpt_system_phase1_for_lang(lang),
#     )
#     reply = finalize_phase1_reply(
#         reply=reply,
#         message=message,
#         preferred_name=preferred_name or getattr(user, "full_name", None),
#         lang=lang,
#     )
#     if not reply:
#         reply = _FALLBACK_EN if lang == "en" else _FALLBACK_FR
#         source = "fallback"
#     return ClientTurnResult(
#         reply=reply.strip(),
#         source="ollama" if source == "ollama" else "fallback",
#         intent="client_agent",
#         llm_provider="ollama" if source == "ollama" else "fallback",
#         agent_mode=True,
#     )
#
#
# def run_client_tool_turn(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     **kwargs: Any,
# ) -> ClientTurnResult:
#     """Tour client via Ollama + outils — le LLM orchestre PDF, export et chat général."""
#     settings = get_settings()
#     ui_language = kwargs.get("ui_language")
#     preferred_name = kwargs.get("preferred_name")
#     response_preferences = kwargs.get("response_preferences")
#     exclude_id = kwargs.get("current_user_message_id")
#     has_image = bool((kwargs.get("image_base64") or "").strip())
#     lang = resolve_ui_language(ui_language, user.preferred_language)
#
#     if not settings.llm_enabled or not settings.gpt_tools_enabled:
#         return ClientTurnResult(
#             reply=_FALLBACK_EN if lang == "en" else _FALLBACK_FR,
#             source="fallback",
#             intent="client_agent",
#         )
#
#     gpt = load_gpt_by_slug(db, SLUG_CLIENT)
#     if gpt is None:
#         logger.warning("client_tool_bridge: GPT fedex-client introuvable")
#         return ClientTurnResult(
#             reply=_FALLBACK_EN if lang == "en" else _FALLBACK_FR,
#             source="fallback",
#             intent="client_agent",
#         )
#
#     resolved_tracking = (kwargs.get("resolved_tracking") or "").strip() or None
#     tracking_source = kwargs.get("tracking_source")
#     phase1 = is_phase1_chat_only()
#
#     if settings.client_conversational_fast_path and not phase1:
#         if is_shipment_question_without_tracking(message, resolved_tracking):
#             return ClientTurnResult(
#                 reply=missing_tracking_prompt(lang),
#                 source="deterministic",
#                 intent="client_agent",
#                 llm_provider="deterministic",
#                 agent_mode=True,
#             )
#         if should_use_conversational_light_path(message, resolved_tracking):
#             return _run_conversational_light_turn(
#                 db,
#                 user=user,
#                 message=message,
#                 session=session,
#                 lang=lang,
#                 ui_language=ui_language,
#                 preferred_name=preferred_name,
#                 exclude_id=exclude_id,
#                 has_image=has_image,
#             )
#
#     memory_ctx = build_memory_context(db, gpt=gpt, user_id=user.id, session_id=session.id)
#     conversation_history = build_conversation_history_for_llm(
#         db,
#         session_id=session.id,
#         exclude_message_id=exclude_id,
#     )
#
#     hits = retrieve_knowledge(db, gpt=gpt, query=message, language=lang, top_k=3, min_score=0.55)
#
#     fedex_facts = None
#     fedex_context = None
#     server_instruction = None
#     if not phase1:
#         fedex_facts = _prefetch_fedex_context(
#             db,
#             user.id,
#             message,
#             resolved_tracking=resolved_tracking,
#             tracking_source=tracking_source,
#         )
#         fedex_context = (fedex_facts.fedex_context_json or None) if fedex_facts else None
#         if resolved_tracking:
#             server_instruction = client_tracking_server_instruction(
#                 tracking_number=resolved_tracking,
#                 tracking_error_code=fedex_facts.error_code if fedex_facts else None,
#             )
#
#     payload = build_gpt_user_payload(
#         message,
#         knowledge_text=format_knowledge_block(hits),
#         memory_text=format_memory_block(memory_ctx),
#         fedex_context=fedex_context,
#         server_instruction=server_instruction,
#         response_preferences=response_preferences,
#         preferred_name=preferred_name or getattr(user, "full_name", None),
#         ui_language=lang,
#         conversation_history=conversation_history,
#     )
#
#     role = (user.role or "client").lower()
#     tools = _filter_tools_by_capabilities(list_tools_for_gpt(gpt, user_role=role))
#     gemini_declarations = gemini_tool_declarations(tools)
#     ollama_declarations = ollama_tool_declarations(tools)
#
#     if phase1:
#         system = client_gpt_system_phase1_for_lang(lang)
#     else:
#         system = f"{client_gpt_system_for_lang(lang)}\n\n{AGENT_TOOLS_SYSTEM_APPEND}"
#
#     tool_ctx = ToolExecutionContext(
#         db=db,
#         user_id=user.id,
#         user_role=role,
#         gpt_slug=SLUG_CLIENT,
#         ui_language=lang,
#         session_id=session.id,
#     )
#
#     tool_payloads: list[dict[str, Any]] = []
#     side_effects: dict[str, Any] = {
#         "export_download": None,
#     }
#
#     pdf_intent = is_pdf_export_intent(message)
#
#     def _on_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
#         result = execute_tool(tool_ctx, ToolCall(name=name, args=args))
#         tool_payloads.append({"name": name, "response": result.to_function_response()})
#         if result.success and result.data.get("export_download"):
#             if pdf_intent:
#                 if name in ("client_export_tracking_pdf", "client_generate_text_pdf"):
#                     side_effects["export_download"] = result.data["export_download"]
#             else:
#                 side_effects["export_download"] = result.data["export_download"]
#         return result.to_function_response()
#
#     if has_image:
#         return ClientTurnResult(
#             reply=(
#                 "Les images ne sont pas encore prises en charge dans ce mode. "
#                 "Décrivez votre demande en texte."
#                 if lang == "fr"
#                 else "Images are not supported in this mode yet. Please describe your request in text."
#             ),
#             source="fallback",
#             intent="client_agent",
#         )
#
#     try:
#         reply, tools_used, llm_provider = _run_tool_agent_loop(
#             system_instruction=system,
#             user_payload=payload,
#             gemini_declarations=gemini_declarations,
#             ollama_declarations=ollama_declarations,
#             on_tool_call=_on_tool,
#             max_rounds=settings.gpt_tool_max_rounds,
#             max_output_tokens=max(gpt.max_output_tokens, 2048),
#         )
#     except Exception:
#         logger.exception("client_tool_bridge tool loop failed")
#         return _resolve_tool_loop_failure(
#             db=db,
#             user=user,
#             message=message,
#             session=session,
#             lang=lang,
#             ui_language=ui_language,
#             preferred_name=preferred_name,
#             response_preferences=response_preferences,
#             conversation_history=conversation_history,
#             exclude_id=exclude_id,
#             fedex_context=fedex_context,
#             resolved_tracking=resolved_tracking,
#             fedex_facts=fedex_facts,
#             has_image=has_image,
#         )
#
#     tracking_number = resolved_tracking or _tracking_from_tool_payloads(tool_payloads)
#
#     if not phase1:
#         _apply_pdf_export_safety_net(
#             db=db,
#             message=message,
#             tool_ctx=tool_ctx,
#             tool_payloads=tool_payloads,
#             side_effects=side_effects,
#             resolved_tracking=resolved_tracking,
#         )
#
#         if tools_used or (side_effects.get("export_download") and tool_payloads):
#             if all_tools_failed(tool_payloads) and not side_effects.get("export_download"):
#                 if is_pdf_export_intent(message):
#                     reply = _pdf_failure_reply(
#                         lang=lang,
#                         message=message,
#                         resolved_tracking=resolved_tracking,
#                         track_error=side_effects.get("pdf_track_error"),
#                     )
#                 elif not message_unrelated_to_shipment(message):
#                     reply = (
#                         "Je n'ai pas pu récupérer les informations demandées. "
#                         "Pouvez-vous préciser votre numéro de suivi FedEx ou reformuler ?"
#                         if lang == "fr"
#                         else "I could not retrieve the requested information. "
#                         "Could you provide your FedEx tracking number or rephrase?"
#                     )
#             else:
#                 synthesized = synthesize_client_tool_turn(
#                     task=message,
#                     tool_payloads=tool_payloads,
#                     ui_language=lang,
#                     preferred_name=preferred_name or getattr(user, "full_name", None),
#                 )
#                 if synthesized:
#                     reply = _reply_text(synthesized) or reply
#
#         elif is_pdf_export_intent(message) and not side_effects.get("export_download"):
#             reply = _pdf_failure_reply(
#                 lang=lang,
#                 message=message,
#                 resolved_tracking=resolved_tracking,
#                 track_error=side_effects.get("pdf_track_error"),
#             )
#
#     if phase1:
#         reply = finalize_phase1_reply(
#             reply=reply,
#             message=message,
#             preferred_name=preferred_name or getattr(user, "full_name", None),
#             lang=lang,
#         )
#         if not reply:
#             reply = _FALLBACK_EN if lang == "en" else _FALLBACK_FR
#             llm_provider = llm_provider or "fallback"
#         return ClientTurnResult(
#             reply=reply.strip(),
#             source="llm",
#             intent="client_agent",
#             llm_provider=llm_provider,
#             agent_mode=True,
#         )
#
#     reply, tracking_number, shipment_payload = finalize_client_tracking_turn(
#         reply=reply,
#         message=message,
#         resolved_tracking=resolved_tracking,
#         fedex_facts=fedex_facts,
#         fedex_context=fedex_context,
#         tools_used=tools_used,
#         lang=lang,
#         preferred_name=preferred_name or getattr(user, "full_name", None),
#         conversation_history=conversation_history,
#         db=db,
#         user=user,
#         session=session,
#     )
#
#     if not reply:
#         reply = _FALLBACK_EN if lang == "en" else _FALLBACK_FR
#         llm_provider = llm_provider or "fallback"
#
#     return ClientTurnResult(
#         reply=reply.strip(),
#         source="llm",
#         intent="client_agent",
#         llm_provider=llm_provider,
#         tracking_number=tracking_number,
#         shipment=shipment_payload,
#         export_download=side_effects.get("export_download"),
#         tools_used=tools_used or None,
#         agent_mode=True,
#     )
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
