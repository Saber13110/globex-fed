"""Requêtes sessions client — alignées sur GET /api/chat/sessions."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.services.client_phase4.transcript_filters import is_boilerplate_for_summary
from app.services.message_attachment import unpack_message_text

_SESSION_LIST_BOT = re.compile(
    r"(conversations récentes|recent conversations|محادثاتك)",
    re.I,
)
_NUMBERED_LINE = re.compile(r"^\s*\d+\.\s+", re.M)


def list_user_sessions(
    db: Session,
    *,
    user_id: int,
    limit: int = 14,
    include_archived: bool = False,
) -> list[ChatSession]:
    stmt = select(ChatSession).where(ChatSession.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(ChatSession.is_archived.is_(False))
    stmt = stmt.order_by(
        ChatSession.is_pinned.desc(),
        ChatSession.updated_at.desc(),
        ChatSession.created_at.desc(),
    ).limit(limit)
    return list(db.scalars(stmt).all())


def get_session_for_user(
    db: Session,
    *,
    user_id: int,
    session_id: int,
) -> ChatSession | None:
    row = db.get(ChatSession, session_id)
    if row is None or row.user_id != user_id:
        return None
    return row


def _is_bot_session_list_message(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    if not _SESSION_LIST_BOT.search(text):
        return False
    return len(_NUMBERED_LINE.findall(text)) >= 2


_DATE_TOLERANCE = timedelta(minutes=15)


def _session_updated_at(session: ChatSession) -> datetime | None:
    updated = session.updated_at
    if updated is None:
        return None
    if updated.tzinfo is None:
        return updated.replace(tzinfo=timezone.utc)
    return updated


def _minutes_apart(a: datetime | None, b: datetime | None) -> float:
    if a is None or b is None:
        return float("inf")
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return abs((a - b).total_seconds()) / 60.0


def _parse_updated_hint(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    return None


def _sessions_matching_hint(sessions: list[ChatSession], hint: str) -> list[ChatSession]:
    hint = (hint or "").strip().lower()
    if not hint:
        return []
    return [s for s in sessions if hint in (s.title or "").lower()]


def _best_session_by_date(
    candidates: list[ChatSession],
    updated_hint: datetime,
    *,
    tolerance_minutes: float = 15.0,
) -> ChatSession | None:
    if not candidates:
        return None
    scored = [
        (s, _minutes_apart(_session_updated_at(s), updated_hint)) for s in candidates
    ]
    within = [(s, d) for s, d in scored if d <= tolerance_minutes]
    if len(within) == 1:
        return within[0][0]
    if within:
        return min(within, key=lambda pair: pair[1])[0]
    return min(scored, key=lambda pair: pair[1])[0]


def _parse_time_hint(raw: object) -> tuple[int, int] | None:
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        try:
            hour = int(raw[0])
            minute = int(raw[1])
        except (TypeError, ValueError):
            return None
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return None


def _clock_minutes_apart(session_dt: datetime | None, hour: int, minute: int) -> float:
    if session_dt is None:
        return float("inf")
    session_clock = session_dt.hour * 60 + session_dt.minute
    target_clock = hour * 60 + minute
    return float(abs(session_clock - target_clock))


def _best_session_by_time(
    candidates: list[ChatSession],
    hour: int,
    minute: int,
    *,
    tolerance_minutes: float = 15.0,
) -> ChatSession | None:
    if not candidates:
        return None
    scored = [
        (s, _clock_minutes_apart(_session_updated_at(s), hour, minute)) for s in candidates
    ]
    within = [(s, d) for s, d in scored if d <= tolerance_minutes]
    if len(within) == 1:
        return within[0][0]
    if within:
        return min(within, key=lambda pair: pair[1])[0]
    return None


def _resolve_by_hint_and_time(
    sessions: list[ChatSession],
    hint: str,
    hour: int,
    minute: int,
) -> ChatSession | None:
    matches = _sessions_matching_hint(sessions, hint)
    if not matches:
        return None
    if len(matches) == 1:
        only = matches[0]
        if _clock_minutes_apart(_session_updated_at(only), hour, minute) <= 15.0:
            return only
        return None
    return _best_session_by_time(matches, hour, minute)


def _resolve_by_hint_and_date(
    sessions: list[ChatSession],
    hint: str,
    updated_hint: datetime | None,
) -> ChatSession | None:
    matches = _sessions_matching_hint(sessions, hint)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    if updated_hint is not None:
        return _best_session_by_date(matches, updated_hint)
    return None


def resolve_session_target(
    db: Session,
    *,
    user_id: int,
    current_session_id: int,
    answers: dict[str, str | int | datetime | tuple[int, int] | None],
) -> tuple[ChatSession | None, list[ChatSession], str | None]:
    """
    Résout la session cible pour summarize_session.
    Retourne (session, ambigu_candidates, error_code).
    Priorité : session_id > list_index (+ vérif date/titre) > session_hint (+ date) > scope.
    """
    sessions = list_user_sessions(db, user_id=user_id, limit=30)
    if not sessions:
        return None, [], "no_sessions"

    hint = str(answers.get("session_hint") or "").strip().lower()
    updated_hint = _parse_updated_hint(answers.get("session_updated_hint"))
    time_hint = _parse_time_hint(answers.get("session_time_hint"))

    raw_id = answers.get("session_id")
    if raw_id is not None:
        try:
            sid = int(raw_id)
        except (TypeError, ValueError):
            sid = 0
        if sid > 0:
            row = get_session_for_user(db, user_id=user_id, session_id=sid)
            if row:
                return row, [], None

    raw_index = answers.get("list_index")
    if raw_index is not None:
        try:
            idx = int(raw_index)
        except (TypeError, ValueError):
            idx = 0
        if idx > 0:
            if 1 <= idx <= len(sessions):
                candidate = sessions[idx - 1]
                if hint and hint not in (candidate.title or "").lower():
                    better = _resolve_by_hint_and_date(sessions, hint, updated_hint)
                    if better is not None:
                        return better, [], None
                if updated_hint is not None:
                    delta = _minutes_apart(_session_updated_at(candidate), updated_hint)
                    if delta > _DATE_TOLERANCE.total_seconds() / 60:
                        better = _resolve_by_hint_and_date(sessions, hint, updated_hint)
                        if better is not None:
                            return better, [], None
                return candidate, [], None
            return None, [], "invalid_index"

    if hint:
        if updated_hint is not None:
            dated = _resolve_by_hint_and_date(sessions, hint, updated_hint)
            if dated is not None:
                return dated, [], None
        if updated_hint is None and time_hint is not None:
            timed = _resolve_by_hint_and_time(sessions, hint, time_hint[0], time_hint[1])
            if timed is not None:
                return timed, [], None
        matches = _sessions_matching_hint(sessions, hint)
        if len(matches) == 1:
            return matches[0], [], None
        if len(matches) > 1:
            return None, matches, "ambiguous"

    scope = str(answers.get("scope") or "").strip().lower()

    if scope == "current":
        row = get_session_for_user(db, user_id=user_id, session_id=current_session_id)
        if row:
            return row, [], None

    if scope == "pinned":
        pinned = [s for s in sessions if s.is_pinned]
        if len(pinned) == 1:
            return pinned[0], [], None
        if len(pinned) > 1:
            return None, pinned, "ambiguous"
        return None, [], "no_pinned"

    if scope == "last":
        return sessions[0], [], None

    if len(sessions) == 1:
        return sessions[0], [], None

    return None, sessions[:5], "ambiguous"


def format_session_line(session: ChatSession, *, index: int, lang: str) -> str:
    title = (session.title or "Conversation").strip()
    updated = session.updated_at
    if updated:
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        date_str = updated.strftime("%d/%m/%Y %H:%M")
    else:
        date_str = "—"
    pin = ""
    if session.is_pinned:
        pin = " 📌" if lang == "fr" else " [pinned]"
    return f"{index}. {title} · {date_str}{pin}"


def build_session_transcript(
    db: Session,
    *,
    session_id: int,
    max_messages: int = 30,
    max_chars: int = 8000,
    for_summary: bool = False,
) -> str:
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(max_messages)
        ).all()
    )
    summary_max = 4000 if for_summary else max_chars
    lines: list[str] = []
    total = 0
    for row in rows:
        text, _, _ = unpack_message_text(row.message_text or "")
        text = (text or "").strip()
        if not text:
            continue
        role = "Utilisateur" if row.sender == MessageSender.user.value else "Assistant"
        if for_summary and role == "Assistant":
            if _is_bot_session_list_message(text) or is_boilerplate_for_summary(text):
                continue
        line = f"{role}: {text}"
        if total + len(line) > summary_max:
            lines.append("…")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def format_relative_sessions_header(lang: str) -> str:
    if lang == "en":
        return "Your recent conversations:"
    if lang == "ar":
        return "محادثاتك الأخيرة:"
    return "Vos conversations récentes :"
