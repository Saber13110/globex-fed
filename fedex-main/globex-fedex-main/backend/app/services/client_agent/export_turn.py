# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Tour export PDF — assistant client."""
#
# from __future__ import annotations
#
# import logging
# import re
# from datetime import datetime, timezone
# from typing import Any
#
# from sqlalchemy import select
# from sqlalchemy.orm import Session
#
# from app.models.chat_message import ChatMessage, MessageSender
# from app.models.chat_session import ChatSession
# from app.models.user import User
# from app.services.ai_assistant.export_dataset_cache import store_client_pdf_blob
# from app.services.chat_export_service import (
#     latest_tracking_rows,
#     resolve_export_targets,
#     session_tracking_numbers,
#     user_recent_tracking_numbers,
# )
# from app.services.chat_session_context import build_conversation_history_for_llm
# from app.services.client_agent.export_routing import (
#     PdfKind,
#     classify_pdf_kind,
#     is_pdf_export_intent,
#     tracking_pdf_preset,
# )
# from app.services.client_agent.pdf_compose import compose_pdf_text_with_ollama
# from app.services.client_agent.types import ClientTurnResult
# from app.services.copilot_export_service import build_export_download_spec
# from app.services.llm.providers import normalize_lang_code
# from app.services.message_attachment import unpack_message_text
# from app.services.simple_text_pdf_service import generate_text_pdf
# from app.utils.pdf_text_extract import extract_custom_pdf_text
#
# logger = logging.getLogger(__name__)
#
#
# def _last_bot_message(db: Session, session_id: int) -> ChatMessage | None:
#     return db.scalars(
#         select(ChatMessage)
#         .where(
#             ChatMessage.session_id == session_id,
#             ChatMessage.sender == MessageSender.bot.value,
#         )
#         .order_by(ChatMessage.created_at.desc())
#         .limit(1)
#     ).first()
#
#
# def _is_export_followup(db: Session, session_id: int) -> bool:
#     last = _last_bot_message(db, session_id)
#     return last is not None and last.source in ("export_prompt",)
#
#
# def should_handle_export_turn(db: Session, session_id: int, message: str) -> bool:
#     if _is_export_followup(db, session_id):
#         return True
#     return is_pdf_export_intent(message)
#
#
# def _adapt_pdf_reply(reply: str | None) -> str | None:
#     if not reply:
#         return reply
#     return (
#         reply.replace("Excel", "PDF")
#         .replace("excel", "PDF")
#         .replace("xlsx", "PDF")
#     )
#
#
# def _ready_reply(
#     *,
#     ui_language: str | None,
#     count: int | None = None,
#     preview: str | None = None,
#     fmt: str = "tracking",
# ) -> str:
#     lang = normalize_lang_code(ui_language)
#     if fmt == "text":
#         if lang == "en":
#             line = "Your PDF is ready."
#             if preview:
#                 line = f"PDF generated: « {preview[:80]} »."
#             return f"{line}\nClick below to download."
#         if lang == "ar":
#             return "ملف PDF جاهز.\nانقر أدناه للتنزيل."
#         line = "Votre PDF est prêt."
#         if preview:
#             line = f"PDF généré : « {preview[:80]} »."
#         return f"{line}\nCliquez ci-dessous pour télécharger."
#
#     if lang == "en":
#         label = f"{count} shipment(s)" if count else "your shipment(s)"
#         return (
#             f"PDF export ready — {label} included.\n"
#             "The file contains FedEx tracking data (status, location, timeline).\n"
#             "Click below to download."
#         )
#     if lang == "ar":
#         return "تصدير PDF جاهز.\nانقر أدناه لتنزيل الملف."
#     label = f"{count} colis" if count else "vos colis"
#     return (
#         f"Export PDF prêt — {label} inclus.\n"
#         "Le fichier contient les **données de suivi FedEx** (statut, localisation, chronologie).\n"
#         "Cliquez ci-dessous pour télécharger."
#     )
#
#
# def _build_tracking_pdf_spec(
#     db: Session,
#     *,
#     user_id: int,
#     session_id: int,
#     tracking_numbers: list[str],
#     preset: str,
# ) -> dict[str, Any]:
#     return {
#         "session_id": session_id,
#         "tracking_numbers": tracking_numbers,
#         "preset": preset,
#         "include_events": True,
#         "format": "pdf",
#     }
#
#
# def _resolve_tracking_numbers_for_scope(
#     db: Session,
#     *,
#     user_id: int,
#     session_id: int,
#     message: str,
#     scope: str = "session",
#     limit: int = 50,
# ) -> list[str]:
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     explicit = (extract_tracking_number(message) or "").strip()
#     if explicit:
#         return [explicit]
#     if scope == "session":
#         tns = session_tracking_numbers(db, session_id, user_id)
#         return tns[:limit] if tns else []
#     return user_recent_tracking_numbers(db, user_id, limit)[:limit]
#
#
# def _handle_tracking_pdf(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     *,
#     ui_language: str | None,
# ) -> ClientTurnResult | None:
#     targets, reply, should_download = resolve_export_targets(db, session.id, user.id, message)
#     reply = _adapt_pdf_reply(reply)
#
#     if should_download and targets:
#         preset = tracking_pdf_preset(message)
#         rows = latest_tracking_rows(
#             db,
#             user_id=user.id,
#             tracking_numbers=targets,
#             session_id=session.id,
#             limit=max(len(targets), 50),
#         )
#         if preset == "tracking_summary":
#             today = datetime.now(timezone.utc).date()
#             rows = [r for r in rows if r.created_at and r.created_at.date() == today]
#         if not rows and targets:
#             rows = latest_tracking_rows(
#                 db,
#                 user_id=user.id,
#                 tracking_numbers=targets,
#                 session_id=session.id,
#                 limit=50,
#             )
#         if not rows:
#             lang = normalize_lang_code(ui_language)
#             err = (
#                 "No shipments to include in the PDF report."
#                 if lang == "en"
#                 else "Aucun suivi à inclure dans le rapport PDF."
#             )
#             return ClientTurnResult(reply=err, source="export", intent="export_pdf")
#
#         tns_final = [r.tracking_number for r in rows]
#         export_download = _build_tracking_pdf_spec(
#             db,
#             user_id=user.id,
#             session_id=session.id,
#             tracking_numbers=tns_final,
#             preset=preset,
#         )
#         return ClientTurnResult(
#             reply=_ready_reply(ui_language=ui_language, count=len(tns_final)),
#             source="export",
#             intent="export_pdf",
#             tracking_number=tns_final[0] if len(tns_final) == 1 else None,
#             export_download=export_download,
#         )
#
#     if reply:
#         return ClientTurnResult(
#             reply=reply,
#             source="export_prompt",
#             intent="export_pdf",
#         )
#     return None
#
#
# def _handle_text_pdf(
#     db: Session,
#     user: User,
#     session: ChatSession,
#     *,
#     text: str,
#     title: str | None,
#     ui_language: str | None,
#     llm_provider: str | None = None,
# ) -> ClientTurnResult:
#     body = (text or "").strip()
#     if not body:
#         lang = normalize_lang_code(ui_language)
#         err = (
#             "I could not find text to put in the PDF."
#             if lang == "en"
#             else "Je n'ai pas trouvé de texte à mettre dans le PDF."
#         )
#         return ClientTurnResult(reply=err, source="export", intent="export_pdf")
#
#     try:
#         pdf_bytes, filename = generate_text_pdf(body, title=title)
#     except ValueError as exc:
#         return ClientTurnResult(reply=str(exc), source="export", intent="export_pdf")
#
#     token = store_client_pdf_blob(
#         user_id=user.id,
#         pdf_bytes=pdf_bytes,
#         filename=filename,
#         meta={"text_preview": body[:200]},
#     )
#     export_download = build_export_download_spec(
#         preset="text_pdf",
#         filename=filename,
#         fmt="pdf",
#         export_token=token,
#         session_id=session.id,
#     )
#     return ClientTurnResult(
#         reply=_ready_reply(ui_language=ui_language, preview=body[:80], fmt="text"),
#         source="export",
#         intent="export_pdf",
#         llm_provider=llm_provider,
#         export_download=export_download,
#     )
#
#
# def handle_export_turn(
#     db: Session,
#     user: User,
#     message: str,
#     session: ChatSession,
#     *,
#     ui_language: str | None = None,
#     exclude_message_id: int | None = None,
# ) -> ClientTurnResult | None:
#     """Gère un tour export PDF. Retourne None si hors contexte."""
#     if not should_handle_export_turn(db, session.id, message):
#         return None
#
#     probe = (message or "").strip()
#     last_bot = _last_bot_message(db, session.id)
#     last_text = ""
#     if last_bot is not None:
#         last_text, _, _ = unpack_message_text(last_bot.message_text or "")
#     has_last = bool(last_text.strip())
#     trackings = session_tracking_numbers(db, session.id, user.id)
#     kind = classify_pdf_kind(
#         probe,
#         has_session_trackings=bool(trackings),
#         has_last_bot_reply=has_last,
#     )
#
#     if kind == PdfKind.tracking or (
#         kind == PdfKind.composed and trackings and re.search(r"\b(pdf|export|rapport)\b", probe, re.I)
#     ):
#         result = _handle_tracking_pdf(db, user, probe, session, ui_language=ui_language)
#         if result is not None:
#             return result
#
#     if kind == PdfKind.free_text:
#         body = extract_custom_pdf_text(probe)
#         if body:
#             return _handle_text_pdf(
#                 db,
#                 user,
#                 session,
#                 text=body,
#                 title=body[:80],
#                 ui_language=ui_language,
#             )
#
#     if kind == PdfKind.wrap_reply and last_bot:
#         body, _, _ = unpack_message_text(last_bot.message_text or "")
#         if body.strip():
#             return _handle_text_pdf(
#                 db,
#                 user,
#                 session,
#                 text=body.strip(),
#                 title="Réponse assistant",
#                 ui_language=ui_language,
#             )
#
#     history_text = build_conversation_history_for_llm(
#         db,
#         session_id=session.id,
#         exclude_message_id=exclude_message_id,
#     )
#
#     if kind in (PdfKind.summary, PdfKind.composed):
#         composed, source = compose_pdf_text_with_ollama(
#             user_request=probe,
#             conversation_text=history_text,
#             ui_language=ui_language,
#         )
#         llm = "ollama" if source == "ollama" else None
#         title = "Résumé de conversation" if normalize_lang_code(ui_language) == "fr" else "Conversation summary"
#         return _handle_text_pdf(
#             db,
#             user,
#             session,
#             text=composed,
#             title=title,
#             ui_language=ui_language,
#             llm_provider=llm,
#         )
#
#     lang = normalize_lang_code(ui_language)
#     err = (
#         "I could not prepare the PDF. Try specifying the content or a tracking number."
#         if lang == "en"
#         else "Je n'ai pas pu préparer le PDF. Précisez le contenu ou un numéro de suivi."
#     )
#     return ClientTurnResult(reply=err, source="export", intent="export_pdf")
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
