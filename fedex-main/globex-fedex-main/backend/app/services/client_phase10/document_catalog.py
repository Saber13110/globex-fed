"""Catalogue documents client — même logique que la page /documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.tracking_request import TrackingRequest
from app.models.user import User
from app.services.client_phase4.session_service import list_user_sessions

DocType = Literal["export", "proof", "report"]

_PROOF_RE = re.compile(r"\b(preuve|proof|pod|livraison|delivery)\b", re.I)
_EXCEL_RE = re.compile(r"\b(excel|xlsx|\.xlsx)\b", re.I)
_REPORT_RE = re.compile(r"\b(rapport|report|pdf|document|facture|invoice)\b", re.I)
_EXPORT_WORD_RE = re.compile(r"\bexport\b", re.I)

_TYPE_LABELS_FR: dict[DocType, str] = {
    "export": "Export Excel",
    "proof": "Preuve de livraison",
    "report": "Rapport",
}
_TYPE_LABELS_EN: dict[DocType, str] = {
    "export": "Excel export",
    "proof": "Proof of delivery",
    "report": "Report",
}

TypeFilter = Literal["all", "export", "proof", "report"]


@dataclass(frozen=True)
class DocumentCatalogItem:
    id: str
    title: str
    doc_type: DocType
    tracking_number: str | None
    session_id: int | None
    history_id: int | None
    created_at: datetime
    source_text: str | None = None


def _lang_code(ui_language: str | None, preferred: str | None = None) -> str:
    code = (ui_language or preferred or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _type_label(doc_type: DocType, lang: str) -> str:
    labels = _TYPE_LABELS_EN if lang == "en" else _TYPE_LABELS_FR
    return labels[doc_type]


def _classify_blob(text: str) -> DocType | None:
    blob = (text or "").lower()
    if _PROOF_RE.search(blob):
        return "proof"
    if _EXCEL_RE.search(blob):
        return "export"
    if _REPORT_RE.search(blob):
        return "report"
    if _EXPORT_WORD_RE.search(blob):
        return "export"
    return None


def _document_title(doc_type: DocType, tracking_number: str | None, lang: str) -> str:
    prefix = _type_label(doc_type, lang)
    tn = (tracking_number or "").strip()
    return f"{prefix} — {tn}" if tn else prefix


def _resolve_session_id(db: Session, user: User, row: TrackingRequest) -> int | None:
    if row.session_id is not None:
        return row.session_id
    stmt = (
        select(ChatMessage.session_id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatSession.user_id == user.id,
            ChatMessage.message_text == row.user_question,
            ChatMessage.sender == MessageSender.user.value,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def build_document_catalog(
    db: Session,
    user: User,
    *,
    ui_language: str | None = None,
    history_limit: int = 100,
    session_limit: int = 80,
) -> list[DocumentCatalogItem]:
    lang = _lang_code(ui_language, user.preferred_language)
    docs: list[DocumentCatalogItem] = []
    seen: set[str] = set()

    stmt = (
        select(TrackingRequest)
        .where(TrackingRequest.user_id == user.id)
        .order_by(TrackingRequest.created_at.desc())
        .limit(history_limit)
    )
    for row in db.scalars(stmt).all():
        blob = f"{row.user_question} {row.bot_response}"
        doc_type = _classify_blob(blob)
        if doc_type is None:
            continue
        session_id = _resolve_session_id(db, user, row)
        key = f"{doc_type}-{row.tracking_number}-{session_id or row.id}"
        if key in seen:
            continue
        seen.add(key)
        docs.append(
            DocumentCatalogItem(
                id=key,
                title=_document_title(doc_type, row.tracking_number, lang),
                doc_type=doc_type,
                tracking_number=(row.tracking_number or "").strip() or None,
                session_id=session_id,
                history_id=row.id,
                created_at=row.created_at,
                source_text=blob,
            )
        )

    sessions = list_user_sessions(
        db,
        user_id=user.id,
        limit=session_limit,
        include_archived=True,
    )
    for sess in sessions:
        doc_type = _classify_blob(sess.title or "")
        if doc_type is None:
            continue
        key = f"session-{sess.id}"
        if key in seen:
            continue
        seen.add(key)
        title = (sess.title or "").strip() or _type_label(doc_type, lang)
        docs.append(
            DocumentCatalogItem(
                id=key,
                title=title,
                doc_type=doc_type,
                tracking_number=None,
                session_id=sess.id,
                history_id=None,
                created_at=sess.updated_at or sess.created_at,
                source_text=sess.title or "",
            )
        )

    docs.sort(key=lambda d: d.created_at, reverse=True)
    return docs


def filter_document_catalog(
    items: list[DocumentCatalogItem],
    *,
    q: str | None = None,
    type_filter: TypeFilter = "all",
    sort_recent: bool = True,
    ui_language: str | None = None,
    preferred_language: str | None = None,
) -> list[DocumentCatalogItem]:
    lang = _lang_code(ui_language, preferred_language)
    rows = list(items)

    query = (q or "").strip().lower()
    if query:
        filtered: list[DocumentCatalogItem] = []
        for doc in rows:
            blob = (
                f"{doc.title} {doc.tracking_number or ''} {_type_label(doc.doc_type, lang)}"
            ).lower()
            if query in blob:
                filtered.append(doc)
        rows = filtered

    if type_filter != "all":
        rows = [d for d in rows if d.doc_type == type_filter]

    rows.sort(key=lambda d: d.created_at, reverse=sort_recent)
    return rows


def format_catalog_list(
    items: list[DocumentCatalogItem],
    *,
    ui_language: str | None = None,
    preferred_language: str | None = None,
    intro: str = "",
) -> str:
    lang = _lang_code(ui_language, preferred_language)
    if not items:
        if lang == "en":
            return (intro + "\n\n" if intro else "") + "No documents match your request."
        return (intro + "\n\n" if intro else "") + "Aucun document ne correspond à votre demande."

    lines: list[str] = []
    if intro:
        lines.append(intro.strip())
        lines.append("")
    for i, doc in enumerate(items, start=1):
        date_str = doc.created_at.strftime("%d/%m/%Y %H:%M")
        lines.append(f"{i}. {doc.title} · {date_str}")

    if lang == "en":
        lines.append("")
        lines.append('Say "download 1" to get a file.')
    else:
        lines.append("")
        lines.append('Dites « télécharge le 1 » pour récupérer un fichier.')
    return "\n".join(lines)
