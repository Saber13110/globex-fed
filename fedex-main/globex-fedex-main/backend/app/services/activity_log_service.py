"""Journalisation centralisée pour la console admin."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog

_TRACKING_RE = re.compile(r"\b\d{10,22}\b")


def mask_sensitive_text(text: str, max_len: int = 500) -> str:
    """Masque partiellement les numéros de suivi dans les messages de log."""
    clipped = (text or "").strip()[:max_len]
    return _TRACKING_RE.sub(lambda m: f"***{m.group(0)[-4:]}", clipped)


def write_log(
    db: Session,
    *,
    action: str,
    message: str,
    category: str = "system",
    level: str = "INFO",
    user_id: int | None = None,
    actor_user_id: int | None = None,
    ip_address: str = "",
    metadata: dict[str, Any] | None = None,
    commit: bool = False,
) -> ActivityLog:
    row = ActivityLog(
        user_id=user_id,
        actor_user_id=actor_user_id,
        level=level.upper()[:16],
        category=category[:32],
        action=action[:64],
        message=mask_sensitive_text(message),
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False)[:8000],
        ip_address=(ip_address or "")[:64],
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def mask_email(email: str) -> str:
    """Masque partiellement l'email pour les journaux (ex. a***@domain.com)."""
    raw = (email or "").strip().lower()
    if "@" not in raw:
        return "***"
    local, domain = raw.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = f"{local[0]}***"
    return f"{masked_local}@{domain}"


def client_ip(request: Any) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return str(request.client.host)[:64]
    return ""
