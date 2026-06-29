"""Proposition e-mail après action admin (suspend, réponse ticket…)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.email.email_types import EmailScenario
from app.services.message_attachment import unpack_message_text

OFFER_MARKER_FR = "Souhaitez-vous notifier l'utilisateur par e-mail"
OFFER_MARKER_EN = "Would you like to notify the user by email"

_PENDING_RE = re.compile(
    r"\[ADMIN_ACTION_EMAIL_OFFER\s+(\{.*?\})\]",
    re.DOTALL,
)
_ACCEPT_RE = re.compile(
    r"^(oui|confirme|yes|ok|confirmer|envoie|envoyer|pr[eé]pare)\b",
    re.I,
)
_DECLINE_RE = re.compile(r"^(non|annule|annuler|cancel|no|pas\s+besoin)\b", re.I)

_NOTIFY_RE = re.compile(
    r"\b("
    r"et\s+(envoie|envoyer|notifie|notifier|pr[eé]venir|prevenir)|"
    r"(envoie|envoyer|notifie|notifier).{0,25}(mail|e-mail|email|courriel)|"
    r"par\s+(mail|e-mail|email)|"
    r"notify.{0,15}(by\s+)?email"
    r")\b",
    re.I,
)


@dataclass
class PendingActionEmailOffer:
    user_id: int
    scenario: str
    admin_note: str = ""
    ticket_id: int | None = None
    ticket_subject: str = ""
    recipient_email: str = ""


def wants_notify_user_by_email(message: str) -> bool:
    """Demande explicite de notifier par e-mail dans le même message que l'action."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_NOTIFY_RE.search(text))


def build_action_email_offer_marker(
    *,
    user_id: int,
    scenario: EmailScenario,
    admin_note: str = "",
    ticket_id: int | None = None,
    ticket_subject: str = "",
    recipient_email: str = "",
) -> str:
    payload = {
        "user_id": user_id,
        "scenario": scenario.value,
        "admin_note": (admin_note or "")[:1500],
        "ticket_id": ticket_id,
        "ticket_subject": (ticket_subject or "")[:200],
        "recipient_email": (recipient_email or "")[:200],
    }
    blob = json.dumps(payload, ensure_ascii=False)
    return f"\n\n[ADMIN_ACTION_EMAIL_OFFER {blob}]"


def offer_suffix(*, lang: str) -> str:
    if lang == "en":
        return (
            f"\n\n_{OFFER_MARKER_EN} ? Reply **yes** to prepare a draft, or **no** to skip._"
        )
    return (
        f"\n\n_{OFFER_MARKER_FR} ? Répondez **oui** pour préparer un brouillon, ou **non** pour ignorer._"
    )


def append_action_email_offer(
    reply: str,
    *,
    user_id: int,
    scenario: EmailScenario,
    admin_note: str = "",
    ticket_id: int | None = None,
    ticket_subject: str = "",
    recipient_email: str = "",
    lang: str = "fr",
) -> str:
    base = (reply or "").strip()
    return (
        base
        + offer_suffix(lang=lang)
        + build_action_email_offer_marker(
            user_id=user_id,
            scenario=scenario,
            admin_note=admin_note,
            ticket_id=ticket_id,
            ticket_subject=ticket_subject,
            recipient_email=recipient_email,
        )
    )


def _has_offer_marker(text: str | None) -> bool:
    blob = text or ""
    return OFFER_MARKER_FR in blob or OFFER_MARKER_EN in blob or bool(_PENDING_RE.search(blob))


def _last_assistant_from_history(conversation_history: list[Any] | None) -> str | None:
    for raw in reversed(conversation_history or []):
        if isinstance(raw, dict):
            role = str(raw.get("role") or "").lower()
            content = str(raw.get("content") or "").strip()
        else:
            role = str(getattr(raw, "role", "") or "").lower()
            content = str(getattr(raw, "content", "") or "").strip()
        if role in ("assistant", "bot") and content:
            return content
    return None


def _recent_bot_texts_by_id(db: Session, session_id: int, *, limit: int = 8) -> list[str]:
    texts: list[str] = []
    for msg in db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.sender == MessageSender.bot.value,
        )
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    ).all():
        text, _, _ = unpack_message_text(msg.message_text or "")
        text = (text or "").strip()
        if text:
            texts.append(text)
    return texts


def latest_offer_bot_text_from_session(db: Session, session_id: int) -> str | None:
    for text in _recent_bot_texts_by_id(db, session_id, limit=12):
        if _has_offer_marker(text):
            return text
    return None


def is_action_email_offer_pending(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_offer_marker(history_text):
        return True
    if _has_offer_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id is not None:
        return latest_offer_bot_text_from_session(db, chat_session_id) is not None
    return False


def parse_action_email_offer(text: str | None) -> PendingActionEmailOffer | None:
    if not text:
        return None
    m = _PENDING_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        user_id = int(data.get("user_id"))
        scenario = str(data.get("scenario") or EmailScenario.custom.value)
        if not user_id:
            return None
        tid = data.get("ticket_id")
        return PendingActionEmailOffer(
            user_id=user_id,
            scenario=scenario,
            admin_note=str(data.get("admin_note") or ""),
            ticket_id=int(tid) if tid is not None else None,
            ticket_subject=str(data.get("ticket_subject") or ""),
            recipient_email=str(data.get("recipient_email") or ""),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def resolve_action_email_offer(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> PendingActionEmailOffer | None:
    offer = parse_action_email_offer(history_text) or parse_action_email_offer(
        _last_assistant_from_history(conversation_history)
    )
    if offer:
        return offer
    if db is not None and chat_session_id is not None:
        return parse_action_email_offer(latest_offer_bot_text_from_session(db, chat_session_id))
    return None


def is_action_email_offer_accept(message: str) -> bool:
    return bool(_ACCEPT_RE.match((message or "").strip()))


def is_action_email_offer_decline(message: str) -> bool:
    return bool(_DECLINE_RE.match((message or "").strip()))
