"""Routeur Phase 10 — bibliothèque documents (liste / filtre / téléchargement)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.client_phase10.capabilities import has_document_library_capability
from app.services.client_phase10.document_catalog import (
    TypeFilter,
    build_document_catalog,
    filter_document_catalog,
    format_catalog_list,
)
from app.services.client_phase10.document_download import build_download_spec, download_ready_message
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

_CONV_RE = re.compile(r"\b(conversations?|discussions?|chats?)\b", re.I)
_DOC_WORKSPACE_RE = re.compile(
    r"\b("
    r"documents?|fichiers?|exports?|preuves?|rapports?|"
    r"mes fichiers|mes documents|page documents|centre documents|"
    r"biblioth[eè]que|compte|mon compte|sidebar|dossiers?|dossier"
    r")\b",
    re.I,
)
_LIST_VERB_RE = re.compile(
    r"\b(liste|lister|montre|montrez|affiche|affichez|voir|quels|quelles|donne|donnez|"
    r"tous|toutes|donne-moi|donnez-moi|affiche-moi|montre-moi)\b",
    re.I,
)
_DOWNLOAD_VERB_RE = re.compile(
    r"\b(t[eé]l[eé]charge|t[eé]l[eé]charger|download|r[eé]cup[eè]re)\b",
    re.I,
)
_TYPE_EXPORT_RE = re.compile(r"\b(exports?|excel|xlsx)\b", re.I)
_TYPE_PROOF_RE = re.compile(r"\b(preuves?|pod|proof)\b", re.I)
_TYPE_REPORT_RE = re.compile(r"\b(rapports?|reports?|pdf)\b", re.I)
_LIST_INDEX_RE = re.compile(
    r"(?:^|[\s:.,;])(?:le|la|l'|the)?\s*(\d{1,2})\s*(?:er|e|ème|eme)?\b",
    re.I,
)
_NUMBERED_TITLE_RE = re.compile(
    r"^\s*(\d+)\.\s+(.+?)\s*·\s*\d{1,2}/\d{1,2}/\d{4}",
    re.M,
)
_PHASE9_EXTRACT_RE = re.compile(
    r"\b(extrait|extrais|contexte du fichier|contenu du fichier|du pdf|dans ce fichier)\b",
    re.I,
)


def _normalize_message(message: str) -> str:
    raw = (message or "").strip().lower()
    folded = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _is_conversation_workspace(message: str) -> bool:
    text = _normalize_message(message)
    if _CONV_RE.search(message or "") and not _DOC_WORKSPACE_RE.search(message or ""):
        return True
    if re.search(r"\b(resume|resumer|recap|synthese)\b", text) and _CONV_RE.search(message or ""):
        return True
    return False


def _is_document_workspace(message: str) -> bool:
    if _PHASE9_EXTRACT_RE.search(message or ""):
        return False
    if _is_conversation_workspace(message):
        return False
    if _DOC_WORKSPACE_RE.search(message or ""):
        return True
    return False


def _looks_like_download_request(message: str) -> bool:
    if not _DOWNLOAD_VERB_RE.search(message or ""):
        return False
    if _parse_list_index(message) is not None:
        return True
    if _is_document_workspace(message):
        return True
    tn = extract_tracking_number(message or "")
    return bool(tn and is_plausible_tracking_number(tn))


def _last_bot_message_text(db: Session, session_id: int) -> str | None:
    row = db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.sender == MessageSender.bot.value,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    ).first()
    return (row.message_text or "").strip() if row else None


def _parse_type_filter(message: str) -> TypeFilter:
    if _TYPE_EXPORT_RE.search(message or ""):
        return "export"
    if _TYPE_PROOF_RE.search(message or ""):
        return "proof"
    if _TYPE_REPORT_RE.search(message or ""):
        return "report"
    return "all"


def _parse_search_query(message: str) -> str | None:
    tn = extract_tracking_number(message or "")
    if tn and is_plausible_tracking_number(tn):
        return tn
    return None


def _looks_like_list_request(message: str) -> bool:
    if not _is_document_workspace(message):
        return False
    if _DOWNLOAD_VERB_RE.search(message or "") and _parse_list_index(message) is None:
        if extract_tracking_number(message or ""):
            return False
    if _DOWNLOAD_VERB_RE.search(message or "") and not _LIST_VERB_RE.search(message or ""):
        return False
    if _LIST_VERB_RE.search(message or ""):
        return True
    text = _normalize_message(message)
    if re.search(r"\b(mes|my)\s+(documents?|fichiers?|exports?)\b", text):
        return True
    if re.search(r"\b(quels|what)\s+(documents?|fichiers?|files)\b", text):
        return True
    if re.search(r"\b(tous|toutes)\s+(les\s+)?(documents?|fichiers?|exports?)\b", text):
        return True
    if re.search(
        r"\b(documents?|fichiers?)\s+(de|du)\s+(mon\s+)?(compte|sidebar|dossier)\b",
        text,
    ):
        return True
    if re.search(r"\b(mes documents|page documents|centre documents)\b", text):
        return True
    return False


def _parse_list_index(message: str) -> int | None:
    match = _LIST_INDEX_RE.search(message or "")
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value >= 1 else None


def _catalog_from_last_list(
    db: Session,
    user: User,
    session_id: int,
    *,
    ui_language: str | None,
) -> list:
    last_bot = _last_bot_message_text(db, session_id) or ""
    matches = list(_NUMBERED_TITLE_RE.finditer(last_bot))
    if not matches:
        return []
    titles = [m.group(2).strip() for m in matches]
    full = build_document_catalog(db, user, ui_language=ui_language)
    by_title = {doc.title: doc for doc in full}
    ordered = []
    for title in titles:
        doc = by_title.get(title)
        if doc is not None:
            ordered.append(doc)
    return ordered


def _resolve_download_item(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    ui_language: str | None,
):
    catalog = _catalog_from_last_list(db, user, session.id, ui_language=ui_language)
    if not catalog:
        catalog = filter_document_catalog(
            build_document_catalog(db, user, ui_language=ui_language),
            type_filter=_parse_type_filter(message),
            q=_parse_search_query(message),
            ui_language=ui_language,
            preferred_language=user.preferred_language,
        )

    idx = _parse_list_index(message)
    if idx is not None and 1 <= idx <= len(catalog):
        return catalog[idx - 1]

    tn = extract_tracking_number(message or "")
    if tn and is_plausible_tracking_number(tn):
        for doc in catalog:
            if doc.tracking_number == tn:
                return doc
        full = build_document_catalog(db, user, ui_language=ui_language)
        for doc in full:
            if doc.tracking_number == tn:
                return doc
    return None


def _turn_result(
    reply: str,
    intent: str,
    *,
    export_download: dict[str, Any] | None = None,
    tracking_number: str | None = None,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "agent_documents",
        "intent": intent,
        "tracking_number": tracking_number,
        "llm_provider": None,
        "shipment": None,
        "export_download": export_download,
    }


def try_client_document_library_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    exclude_message_id: int | None,
    ui_language: str | None,
) -> dict[str, Any] | None:
    del exclude_message_id  # réservé pour extension future
    if not has_document_library_capability():
        return None

    lang = _lang(ui_language, user)

    if _looks_like_download_request(message):
        item = _resolve_download_item(db, user, session, message, ui_language=ui_language)
        if item is None:
            if lang == "en":
                reply = "I could not find that document. List your documents first, then say e.g. « download 1 »."
            else:
                reply = (
                    "Je n'ai pas trouvé ce document. Listez d'abord vos documents, "
                    "puis dites par exemple « télécharge le 1 »."
                )
            return _turn_result(reply, "download_document")
        spec = build_download_spec(item)
        reply = download_ready_message(item, lang=lang)
        return _turn_result(
            reply,
            "download_document",
            export_download=spec,
            tracking_number=item.tracking_number,
        )

    if _looks_like_list_request(message):
        catalog = build_document_catalog(db, user, ui_language=ui_language)
        filtered = filter_document_catalog(
            catalog,
            type_filter=_parse_type_filter(message),
            q=_parse_search_query(message),
            ui_language=ui_language,
            preferred_language=user.preferred_language,
        )
        if lang == "en":
            intro = "Here are your documents:"
        else:
            intro = "Voici vos documents :"
        reply = format_catalog_list(
            filtered,
            ui_language=ui_language,
            preferred_language=user.preferred_language,
            intro=intro,
        )
        return _turn_result(reply, "list_documents")

    return None
