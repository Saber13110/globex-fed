"""PDF texte libre admin — génère un PDF à partir de la demande utilisateur.

Intercepte les demandes du type « génère un PDF qui contient bonjour » ou
« genere salut dans un pdf » avant `handle_pdf_only_followup_turn`.
Admin uniquement : ne modifie pas le portail client.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.admin_client.capabilities import has_admin_capability
from app.services.client_phase3.capabilities import CAP_PDF, has_capability
from app.services.client_phase3.export_router import _capability_disabled_reply
from app.services.client_phase3.pdf_body_composer import short_pdf_chat_reply
from app.services.client_phase3.pdf_postprocess import (
    is_conversation_or_transcript_pdf_request,
    wants_pdf_format,
)
from app.services.client_phase3.pdf_text import (
    append_pdf_ready_note,
    build_text_pdf_download,
    draft_pdf_content,
)
from app.services.chat_export_service import session_tracking_numbers
from app.services.llm.providers import LlmProviderError
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

_GENERATIVE = re.compile(
    r"\b(g[eé]?n[eè]?r\w*|cr[eé][eé]\w*|fais\w*|make\w*|create\w*|write\w*|r[eé]dig\w*|produce\w*)\b",
    re.IGNORECASE,
)
_CONTENT_MARKER = re.compile(
    r"\b(contient|contenant|avec\s+le\s+texte|qui\s+dit|including|containing)\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'[«"]([^»"]+)[»"]|\'([^\']+)\'')
_LITERAL_AFTER = re.compile(
    r"(?:contient|contenant|including|containing|avec\s+le\s+texte|qui\s+dit)\s+(.+?)"
    r"(?:\s+en\s+pdf|\s*$)",
    re.IGNORECASE,
)
_GENERATE_DANS_PDF = re.compile(
    r"(?:g[eé]n[eè]r\w*|cr[eé][eé]\w*|fais\w*)\s+(?:moi\s+)?(?:un\s+)?(?:pdf\s+)?(.+?)\s+"
    r"(?:dans\s+un\s+pdf|en\s+pdf|au\s+format\s+pdf)\s*$",
    re.IGNORECASE,
)
_METS_EN_PDF = re.compile(
    r"\b(mets?|met)\s+(.+?)\s+(?:en\s+pdf|au\s+format\s+pdf|dans\s+un\s+pdf)\s*$",
    re.IGNORECASE,
)
_FAIS_AVEC = re.compile(
    r"\bfais\w*\s+(?:moi\s+)?(?:un\s+)?pdf\s+(?:avec|contenant|contient)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_PURE_FOLLOWUP = re.compile(
    r"^(?:mets?|met|exporte?|donne(?:\s+moi)?|convertis|transforme)\s+"
    r"(?:le|la|les|ça|cela|this|it|moi)?\s*"
    r"(?:en\s+)?(?:pdf|document)\s*\.?$",
    re.IGNORECASE,
)

_DEFAULT_TITLE = "Document FedEx Globex"


def _lang_code(ui_language: str | None, user: User) -> str:
    return (ui_language or user.preferred_language or "fr").lower()[:2]


def _clean_literal_body(raw: str) -> str:
    body = (raw or "").strip().strip("\"'«»").strip()
    body = re.sub(r"^(?:le\s+texte|un\s+pdf|pdf)\s+", "", body, flags=re.IGNORECASE)
    return body.strip()


def is_free_text_pdf_request(message: str, *, has_session_tracking: bool = False) -> bool:
    """Vrai si l'admin demande un PDF avec nouveau contenu (pas une relance pure)."""
    text = (message or "").strip()
    if not wants_pdf_format(text):
        return False
    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request

    if is_admin_shipment_pdf_request(text, has_session_tracking=has_session_tracking):
        return False
    if is_conversation_or_transcript_pdf_request(text):
        return False
    if extract_tracking_number(text):
        return False
    if _PURE_FOLLOWUP.match(text):
        return False
    if extract_literal_pdf_body(text):
        return True
    has_new_content = bool(
        _GENERATIVE.search(text) or _CONTENT_MARKER.search(text) or _QUOTED.search(text)
    )
    if len(text) <= 80 and not has_new_content:
        return False
    if has_new_content:
        return True
    return len(text) > 80


def extract_literal_pdf_body(message: str) -> str | None:
    """Extrait un corps PDF literal (guillemets, contient, genere X dans un pdf, …)."""
    text = (message or "").strip()
    quoted = _QUOTED.search(text)
    if quoted:
        body = _clean_literal_body(quoted.group(1) or quoted.group(2) or "")
        return body or None

    patterns: list[tuple[re.Pattern[str], int]] = [
        (_GENERATE_DANS_PDF, 1),
        (_METS_EN_PDF, 2),
        (_FAIS_AVEC, 1),
    ]
    for pattern, group_idx in patterns:
        match = pattern.search(text)
        if match:
            body = _clean_literal_body(match.group(group_idx))
            if body:
                return body

    match = _LITERAL_AFTER.search(text)
    if not match:
        return None
    body = _clean_literal_body(match.group(1))
    return body or None


def _pdf_disabled_turn(admin: User, ui_language: str | None) -> dict[str, Any]:
    return {
        "reply": _capability_disabled_reply(ui_language, admin, "export PDF"),
        "source": "admin_client",
        "intent": "export_pdf_disabled",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }


def _pdf_error_turn(admin: User, ui_language: str | None, detail: str) -> dict[str, Any]:
    lang = _lang_code(ui_language, admin)
    if not detail.strip():
        detail = (
            "Impossible de générer le document PDF. Reformulez votre demande."
            if lang != "en"
            else "Could not generate the PDF document. Please rephrase your request."
        )
    return {
        "reply": detail,
        "source": "admin_client",
        "intent": "export_pdf_error",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }


def _export_turn(
    admin: User,
    export_download: dict[str, Any],
    reply: str,
    *,
    llm_provider: str | None = None,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": None,
        "llm_provider": llm_provider,
        "shipment": None,
        "export_download": export_download,
    }


def _admin_draft_and_build_pdf(
    admin: User,
    session: ChatSession,
    message: str,
    ui_language: str | None,
) -> tuple[str, dict[str, Any]]:
    """Rédige le PDF via Ollama sans historique session (évite le contexte suivi colis)."""
    lang = _lang_code(ui_language, admin)
    try:
        body = draft_pdf_content(
            message,
            conversation_history=None,
            ui_language=ui_language,
        )
    except LlmProviderError:
        logger.warning("Admin free-text PDF draft failed", exc_info=True)
        err = (
            "Désolé, je n'ai pas pu rédiger le contenu du PDF pour le moment. "
            "Réessayez plus tard ou précisez le texte avec « contient … »."
            if lang != "en"
            else "Sorry, I could not draft the PDF content right now. "
            "Try again later or specify the text with « contains … »."
        )
        return err, {}

    try:
        export_download = build_text_pdf_download(
            admin.id,
            body,
            title=_DEFAULT_TITLE,
            session_id=session.id,
        )
    except ValueError as exc:
        return str(exc), {}

    reply = append_pdf_ready_note(short_pdf_chat_reply(lang, doc_title=_DEFAULT_TITLE))
    return reply, export_download


def try_admin_free_text_pdf_turn(
    db: Session,
    admin: User,
    session: ChatSession,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Génère un PDF libre (literal ou LLM) pour l'admin, ou None si hors scope."""
    del user_msg_id  # réservé pour extension ; pas d'historique session injecté
    session_tns = session_tracking_numbers(db, session.id, admin.id)
    if not is_free_text_pdf_request(
        message, has_session_tracking=bool(session_tns)
    ):
        return None
    if not has_admin_capability(CAP_PDF) and not has_capability(CAP_PDF):
        return _pdf_disabled_turn(admin, ui_language)

    lang = _lang_code(ui_language, admin)
    literal_body = extract_literal_pdf_body(message)

    if literal_body:
        try:
            export_download = build_text_pdf_download(
                admin.id,
                literal_body,
                title=_DEFAULT_TITLE,
                session_id=session.id,
            )
        except ValueError as exc:
            return _pdf_error_turn(admin, ui_language, str(exc))
        reply = append_pdf_ready_note(
            short_pdf_chat_reply(lang, doc_title=_DEFAULT_TITLE)
        )
        return _export_turn(admin, export_download, reply)

    reply, export_download = _admin_draft_and_build_pdf(
        admin, session, message, ui_language
    )
    if not export_download:
        return _pdf_error_turn(admin, ui_language, reply)

    return _export_turn(admin, export_download, reply, llm_provider="ollama")
