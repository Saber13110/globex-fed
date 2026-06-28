"""Phase 3b — PDF post-réponse : le chat rédige d'abord, fpdf emballe ensuite."""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_session_context import build_conversation_history_for_llm
from app.services.client_phase3.capabilities import CAP_PDF, has_capability
from app.services.client_phase3.export_intent import is_pdf_export_intent
from app.services.client_phase3.export_router import _capability_disabled_reply
from app.services.client_phase3.pdf_body_composer import (
    build_pdf_body_for_shipment_turn,
    short_pdf_chat_reply,
    strip_markdown_for_pdf,
)
from app.services.client_phase3.pdf_text import (
    build_session_transcript_text,
    build_text_pdf_artifact,
    build_text_pdf_download,
    draft_pdf_content,
    last_bot_message_text,
    recent_bot_message_texts,
)
from app.services.client_phase7.export_email_hook import (
    email_tracking_pdf_export,
    finalize_export_delivery,
)
from app.services.client_phase7.export_email_intent import wants_export_by_email
from app.services.client_phase3.pdf_tracking import run_tracking_pdf_export
from app.services.llm.providers import LlmProviderError
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

_CONVERSATION_SUMMARY = re.compile(
    r"\b(r[eé]sum[eé]|synth[eè]se|recap|r[eé]capitulatif|historique\s+chat)\b",
    re.I,
)
_DISCUSSION_TRANSCRIPT = re.compile(
    r"\b(conversation|discussion|notre\s+discussion|cette\s+discussion|historique\s+du\s+chat)\b",
    re.I,
)
_TECHNICAL_TRACKING = re.compile(
    r"\b(historique\s+scans?|rapport\s+technique|export\s+tracking\s+officiel|scans?\s+fedex)\b",
    re.I,
)
_FOLLOWUP_REF = re.compile(
    r"\b("
    r"ces\s+infos?|cette\s+r[eé]ponse|ta\s+r[eé]ponse|ton\s+r[eé]ponse|"
    r"ce\s+que\s+tu\s+(viens\s+de\s+)?(dire|dit)|derni[eè]re\s+r[eé]ponse|"
    r"mets?\s+[çc]a|met\s+[çc]a|sous\s+forme|donne\s+(moi\s+)?(ces|ça)|"
    r"en\s+pdf|au\s+format\s+pdf"
    r")\b",
    re.I,
)
_TRACKING_IN_MSG = re.compile(
    r"\b(colis|suivi|tracking|livraison|exp[eé]dition|shipments?)\b",
    re.I,
)


class PdfBodyKind(str, Enum):
    followup = "followup"
    same_turn = "same_turn"
    conversation = "conversation"
    technical_tracking = "technical_tracking"


def _finalize_text_pdf_reply(
    user: User,
    session: ChatSession,
    message: str,
    reply: str,
    pdf_body: str,
    *,
    title: str,
    doc_label: str,
    ui_language: str | None,
) -> tuple[str, dict[str, Any]]:
    spec, pdf_bytes, filename = build_text_pdf_artifact(
        user.id,
        pdf_body,
        title=title,
        session_id=session.id,
    )
    return finalize_export_delivery(
        user,
        session.id,
        message,
        reply,
        spec,
        pdf_bytes,
        filename,
        "pdf",
        doc_label,
        ui_language=ui_language,
    )


def wants_pdf_format(message: str) -> bool:
    return is_pdf_export_intent(message)


def is_discussion_transcript_request(message: str) -> bool:
    """Export fidèle discussion/conversation en PDF — sans Ollama."""
    text = (message or "").strip()
    if not wants_pdf_format(text):
        return False
    if _CONVERSATION_SUMMARY.search(text):
        return False
    return bool(_DISCUSSION_TRANSCRIPT.search(text))


def is_conversation_summary_request(message: str) -> bool:
    """Résumé/synthèse explicite + format PDF."""
    text = (message or "").strip()
    return wants_pdf_format(text) and bool(_CONVERSATION_SUMMARY.search(text))


def is_conversation_or_transcript_pdf_request(message: str) -> bool:
    return is_discussion_transcript_request(message) or is_conversation_summary_request(message)


def is_technical_tracking_pdf_request(message: str) -> bool:
    return bool(_TECHNICAL_TRACKING.search(message or ""))


def is_pdf_only_followup(message: str) -> bool:
    """Demande PDF sans nouvelle question (ex. « ces infos en pdf »)."""
    text = (message or "").strip()
    if not wants_pdf_format(text):
        return False
    if extract_tracking_number(text):
        return False
    if is_discussion_transcript_request(text):
        return False
    if is_conversation_summary_request(text):
        return False
    if is_technical_tracking_pdf_request(text):
        return False
    if _TRACKING_IN_MSG.search(text) and len(text) > 40:
        return False
    if _FOLLOWUP_REF.search(text):
        return True
    if len(text) <= 80 and wants_pdf_format(text):
        return True
    return False


def _lang_code(ui_language: str | None, user: User) -> str:
    return (ui_language or user.preferred_language or "fr").lower()[:2]


def clarify_pdf_followup(
    db: Session,
    session: ChatSession,
    user: User,
    message: str,
    ui_language: str | None,
) -> str | None:
    """Retourne un message de clarification si la demande PDF est ambiguë."""
    last = last_bot_message_text(db, session.id)
    if not last:
        lang = _lang_code(ui_language, user)
        if lang == "en":
            return (
                "I don't have a previous reply to put in a PDF yet. "
                "Ask your question first (e.g. track a package), then ask for the PDF."
            )
        return (
            "Je n'ai pas encore de réponse à mettre en PDF. "
            "Posez d'abord votre question (ex. suivi d'un colis), puis redemandez le PDF."
        )

    recent = recent_bot_message_texts(db, session.id, limit=3)
    if len(recent) >= 2:
        tns_last = extract_tracking_number(recent[0] or "")
        tns_prev = extract_tracking_number(recent[1] or "")
        if tns_last and tns_prev and tns_last != tns_prev:
            lang = _lang_code(ui_language, user)
            if lang == "en":
                return (
                    f"I see several recent replies. Do you want:\n"
                    f"1. A PDF of my last reply about package **{tns_last}**\n"
                    f"2. A PDF summary of our whole conversation?\n\n"
                    f"Reply with option 1 or 2, or rephrase your request."
                )
            return (
                f"Je vois plusieurs réponses récentes. Souhaitez-vous :\n"
                f"1. Un PDF de ma dernière réponse sur le colis **{tns_last}**\n"
                f"2. Un PDF résumé de toute notre conversation ?\n\n"
                f"Répondez par 1 ou 2, ou reformulez votre demande."
            )
    return None


def _classify_pdf_body_kind(message: str, *, pdf_only_followup: bool) -> PdfBodyKind:
    if is_technical_tracking_pdf_request(message):
        return PdfBodyKind.technical_tracking
    if is_conversation_summary_request(message):
        return PdfBodyKind.conversation
    if pdf_only_followup:
        return PdfBodyKind.followup
    return PdfBodyKind.same_turn


def handle_pdf_only_followup_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Traite les demandes PDF pures (sans nouvelle question) avant Phase 2."""
    if not is_pdf_only_followup(message):
        return None
    if not has_capability(CAP_PDF):
        return {
            "reply": _capability_disabled_reply(ui_language, user, "export PDF"),
            "source": "phase3",
            "intent": "export_pdf_disabled",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }

    clarification = clarify_pdf_followup(db, session, user, message, ui_language)
    if clarification:
        return {
            "reply": clarification,
            "source": "phase3",
            "intent": "export_pdf_clarify",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }

    last_bot = last_bot_message_text(db, session.id)
    if not last_bot:
        return None

    lang = _lang_code(ui_language, user)
    pdf_body, tn_used = build_pdf_body_for_shipment_turn(
        message,
        last_bot_text=last_bot,
        chat_context=None,
        tracking_number=None,
        lang=lang,
    )
    if not pdf_body:
        pdf_body = strip_markdown_for_pdf(last_bot)

    title = f"Suivi colis {tn_used}" if tn_used else "Réponse assistant FedEx"
    try:
        reply = short_pdf_chat_reply(lang, doc_title=title)
        reply, export_download = _finalize_text_pdf_reply(
            user,
            session,
            message,
            reply,
            pdf_body,
            title=title,
            doc_label=title,
            ui_language=ui_language,
        )
    except ValueError as exc:
        return _pdf_error_turn(ui_language, user, exc)

    return {
        "reply": reply,
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": tn_used or extract_tracking_number(last_bot),
        "llm_provider": "ollama",
        "shipment": None,
        "export_download": export_download,
    }


def _empty_transcript_reply(ui_language: str | None, user: User) -> str:
    lang = _lang_code(ui_language, user)
    if lang == "en":
        return (
            "There are not enough messages in this conversation to generate a PDF yet. "
            "Exchange a few messages first, then try again."
        )
    return (
        "Il n'y a pas encore assez de messages dans cette conversation pour générer un PDF. "
        "Échangez quelques messages, puis réessayez."
    )


def _summary_fallback_note(ui_language: str | None, user: User) -> str:
    lang = _lang_code(ui_language, user)
    if lang == "en":
        return (
            "Note: the summary could not be generated in time; "
            "the PDF contains the full conversation transcript."
        )
    return (
        "Note : le résumé n'a pas pu être généré à temps ; "
        "le PDF contient le transcript complet de la conversation."
    )


def _pdf_generation_error_reply(ui_language: str | None, user: User) -> str:
    lang = _lang_code(ui_language, user)
    if lang == "en":
        return "Unable to generate the PDF file. Please try again or rephrase your request."
    return "Impossible de générer le fichier PDF. Réessayez ou reformulez votre demande."


def _pdf_error_turn(
    ui_language: str | None,
    user: User,
    exc: ValueError | None = None,
) -> dict[str, Any]:
    reply = str(exc).strip() if exc and str(exc).strip() else _pdf_generation_error_reply(ui_language, user)
    return {
        "reply": reply,
        "source": "phase3",
        "intent": "export_pdf_error",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }


def _build_conversation_pdf_result(
    user: User,
    session: ChatSession,
    body: str,
    *,
    title: str,
    message: str = "",
    llm_provider: str | None = None,
    prefix_note: str | None = None,
    ui_language: str | None = None,
) -> dict[str, Any]:
    pdf_body = body
    if prefix_note:
        pdf_body = f"{prefix_note}\n\n{body}"
    lang = _lang_code(ui_language, user)
    reply = short_pdf_chat_reply(lang, doc_title=title)
    try:
        reply, export_download = _finalize_text_pdf_reply(
            user,
            session,
            message,
            reply,
            pdf_body,
            title=title,
            doc_label=title,
            ui_language=ui_language,
        )
    except ValueError as exc:
        raise exc
    return {
        "reply": reply,
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": None,
        "llm_provider": llm_provider,
        "shipment": None,
        "export_download": export_download,
    }


def handle_conversation_pdf_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Transcript ou résumé de conversation en PDF — avant Phase 2."""
    if not is_conversation_or_transcript_pdf_request(message):
        return None
    if not has_capability(CAP_PDF):
        return {
            "reply": _capability_disabled_reply(ui_language, user, "export PDF"),
            "source": "phase3",
            "intent": "export_pdf_disabled",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }

    if is_discussion_transcript_request(message):
        body = build_session_transcript_text(
            db,
            session.id,
            exclude_message_id=user_msg_id,
        )
        if not body:
            return {
                "reply": _empty_transcript_reply(ui_language, user),
                "source": "phase3",
                "intent": "export_pdf_clarify",
                "tracking_number": None,
                "llm_provider": None,
                "shipment": None,
                "export_download": None,
            }
        try:
            return _build_conversation_pdf_result(
                user,
                session,
                body,
                title="Conversation FedEx Globex",
                message=message,
                llm_provider=None,
                ui_language=ui_language,
            )
        except ValueError as exc:
            return _pdf_error_turn(ui_language, user, exc)

    history = build_conversation_history_for_llm(
        db,
        session_id=session.id,
        exclude_message_id=user_msg_id,
        limit=8,
    )
    prefix_note: str | None = None
    try:
        body = draft_pdf_content(
            message,
            conversation_history=history,
            ui_language=ui_language,
        )
    except LlmProviderError:
        logger.warning("Conversation PDF summary failed, fallback transcript", exc_info=True)
        body = build_session_transcript_text(
            db,
            session.id,
            exclude_message_id=user_msg_id,
        )
        if not body:
            lang = _lang_code(ui_language, user)
            err = (
                "Sorry, I could not draft the PDF content. Please try again later."
                if lang == "en"
                else "Désolé, je n'ai pas pu rédiger le contenu du PDF. Réessayez plus tard."
            )
            return {
                "reply": err,
                "source": "phase3",
                "intent": "export_pdf_error",
                "tracking_number": None,
                "llm_provider": None,
                "shipment": None,
                "export_download": None,
            }
        prefix_note = _summary_fallback_note(ui_language, user)

    try:
        return _build_conversation_pdf_result(
            user,
            session,
            body,
            title="Résumé FedEx Globex",
            message=message,
            llm_provider="ollama" if prefix_note is None else None,
            prefix_note=prefix_note,
            ui_language=ui_language,
        )
    except ValueError as exc:
        return _pdf_error_turn(ui_language, user, exc)


def maybe_attach_pdf_export(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    chat_reply: str,
    tracking_number: str | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """
    Après Phase 2 : emballe chat_reply en PDF si demandé.
    Retourne (reply_finale, export_download, intent_override).
    """
    if not wants_pdf_format(message):
        return chat_reply, None, None

    if not has_capability(CAP_PDF):
        disabled = _capability_disabled_reply(ui_language, user, "export PDF")
        return disabled, None, "export_pdf_disabled"

    kind = _classify_pdf_body_kind(message, pdf_only_followup=False)

    lang = _lang_code(ui_language, user)

    if kind == PdfBodyKind.technical_tracking:
        tech_reply, export_dl, tn = run_tracking_pdf_export(
            db, user, session, message, ui_language=ui_language
        )
        if export_dl:
            title = f"Suivi colis {tn}" if tn else "Historique FedEx"
            reply = short_pdf_chat_reply(lang, doc_title=title)
            if wants_export_by_email(message):
                reply = email_tracking_pdf_export(
                    db,
                    user,
                    session.id,
                    message,
                    reply,
                    export_dl,
                    ui_language=ui_language,
                    doc_label=title,
                )
            return reply, export_dl, "export_pdf"
        last_bot = last_bot_message_text(db, session.id)
        pdf_body, tn_used = build_pdf_body_for_shipment_turn(
            message,
            last_bot_text=last_bot,
            chat_context=chat_reply,
            tracking_number=tracking_number or tn,
            lang=lang,
        )
        if not pdf_body:
            pdf_body = strip_markdown_for_pdf((chat_reply or "").strip() or (last_bot or ""))
        if not pdf_body:
            return tech_reply, None, "export_pdf_error"
        title = f"Suivi colis {tn_used or tn or tracking_number}" if (tn_used or tn or tracking_number) else "Réponse assistant FedEx"
        try:
            reply = short_pdf_chat_reply(lang, doc_title=title)
            reply, export_download = _finalize_text_pdf_reply(
                user,
                session,
                message,
                reply,
                pdf_body,
                title=title,
                doc_label=title,
                ui_language=ui_language,
            )
        except ValueError:
            return tech_reply, None, "export_pdf_error"
        return reply, export_download, "export_pdf"

    if kind == PdfBodyKind.conversation:
        clarification = clarify_pdf_followup(db, session, user, message, ui_language)
        if clarification:
            return clarification, None, "export_pdf_clarify"
        history = build_conversation_history_for_llm(
            db,
            session_id=session.id,
            exclude_message_id=user_msg_id,
            limit=8,
        )
        prefix_note: str | None = None
        try:
            pdf_body = draft_pdf_content(
                message,
                conversation_history=history,
                ui_language=ui_language,
            )
            llm_used = "ollama"
        except LlmProviderError:
            logger.warning("Same-turn conversation PDF summary failed, fallback transcript", exc_info=True)
            pdf_body = build_session_transcript_text(
                db,
                session.id,
                exclude_message_id=user_msg_id,
            )
            llm_used = None
            if not pdf_body:
                err = _pdf_generation_error_reply(ui_language, user)
                return err, None, "export_pdf_error"
            prefix_note = _summary_fallback_note(ui_language, user)
        if prefix_note:
            pdf_body = f"{prefix_note}\n\n{pdf_body}"
        title = "Résumé FedEx Globex"
        try:
            reply = short_pdf_chat_reply(lang, doc_title=title)
            reply, export_download = _finalize_text_pdf_reply(
                user,
                session,
                message,
                reply,
                pdf_body,
                title=title,
                doc_label=title,
                ui_language=ui_language,
            )
        except ValueError:
            return _pdf_generation_error_reply(ui_language, user), None, "export_pdf_error"
        return reply, export_download, "export_pdf"

    last_bot = last_bot_message_text(db, session.id)
    pdf_body, tn_used = build_pdf_body_for_shipment_turn(
        message,
        last_bot_text=last_bot,
        chat_context=chat_reply,
        tracking_number=tracking_number,
        lang=lang,
    )
    if not pdf_body:
        clarification = clarify_pdf_followup(db, session, user, message, ui_language)
        if clarification:
            return clarification, None, "export_pdf_clarify"
        err = (
            "I could not prepare the PDF document. Please rephrase your request."
            if lang == "en"
            else "Je n'ai pas pu préparer le document PDF. Reformulez votre demande."
        )
        return err, None, "export_pdf_error"

    title = "Réponse assistant FedEx"
    if tn_used or tracking_number:
        title = f"Suivi colis {tn_used or tracking_number}"

    try:
        reply = short_pdf_chat_reply(lang, doc_title=title)
        reply, export_download = _finalize_text_pdf_reply(
            user,
            session,
            message,
            reply,
            pdf_body,
            title=title,
            doc_label=title,
            ui_language=ui_language,
        )
    except ValueError:
        return _pdf_generation_error_reply(ui_language, user), None, "export_pdf_error"

    return reply, export_download, "export_pdf"
