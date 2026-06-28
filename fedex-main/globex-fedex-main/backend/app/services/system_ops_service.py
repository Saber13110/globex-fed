"""Opérations système : cache, réindexation, sauvegarde."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.user import User
from app.schemas.system_settings import SystemOperationResponse
from app.services import fedex_service
from app.services.rate_limit_service import clear_all_rate_limits


def clear_cache() -> SystemOperationResponse:
    cleared = clear_all_rate_limits()
    fedex_service._TOKEN_CACHE["access_token"] = None
    fedex_service._TOKEN_CACHE["expires_at"] = 0.0
    return SystemOperationResponse(
        ok=True,
        message="Cache vidé avec succès.",
        detail={"rate_limit_keys_cleared": cleared, "fedex_token_cache": True},
    )


def reindex_data(db: Session) -> SystemOperationResponse:
    tables = ["users", "chat_sessions", "chat_messages", "activity_logs", "tracking_requests"]
    analyzed: list[str] = []
    for table in tables:
        try:
            db.execute(text(f"ANALYZE {table}"))
            analyzed.append(table)
        except Exception:  # noqa: BLE001
            continue
    db.commit()
    return SystemOperationResponse(
        ok=True,
        message="Réindexation terminée.",
        detail={"tables_analyzed": analyzed},
    )


def manual_backup(db: Session) -> SystemOperationResponse:
    root = Path(__file__).resolve().parents[2]
    backup_dir = root / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"backup_{stamp}.json"

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "users": int(db.scalar(select(func.count()).select_from(User)) or 0),
            "sessions": int(db.scalar(select(func.count()).select_from(ChatSession)) or 0),
            "messages": int(db.scalar(select(func.count()).select_from(ChatMessage)) or 0),
            "activity_logs": int(db.scalar(select(func.count()).select_from(ActivityLog)) or 0),
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return SystemOperationResponse(
        ok=True,
        message="Sauvegarde créée.",
        detail={"path": str(path), "counts": payload["counts"]},
    )
