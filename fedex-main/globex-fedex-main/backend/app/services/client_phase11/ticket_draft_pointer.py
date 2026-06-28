"""Cache brouillon ticket par session — TTL 30 min."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

_TTL_SECONDS = 1800
_drafts: dict[int, tuple[float, dict[str, Any]]] = {}


@dataclass
class TicketDraft:
    subject: str
    message: str
    category: str
    priority: str
    tracking_number: str | None = None


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (exp, _) in _drafts.items() if exp <= now]
    for k in expired:
        _drafts.pop(k, None)


def set_ticket_draft(session_id: int, draft: dict[str, Any]) -> None:
    _purge_expired()
    _drafts[int(session_id)] = (time.time() + _TTL_SECONDS, dict(draft))


def get_ticket_draft(session_id: int) -> TicketDraft | None:
    _purge_expired()
    entry = _drafts.get(int(session_id))
    if not entry:
        return None
    expires, payload = entry
    if expires <= time.time():
        _drafts.pop(int(session_id), None)
        return None
    subject = str(payload.get("subject") or "").strip()
    message = str(payload.get("message") or "").strip()
    if len(subject) < 3 or len(message) < 10:
        return None
    tn = str(payload.get("tracking_number") or "").strip() or None
    return TicketDraft(
        subject=subject,
        message=message,
        category=str(payload.get("category") or "other"),
        priority=str(payload.get("priority") or "medium"),
        tracking_number=tn,
    )


def clear_ticket_draft(session_id: int) -> None:
    _drafts.pop(int(session_id), None)
