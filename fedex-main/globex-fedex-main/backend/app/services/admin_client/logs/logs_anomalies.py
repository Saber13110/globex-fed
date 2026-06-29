"""Règles d'anomalie sur journaux d'activité."""

from __future__ import annotations

from typing import Any


def analyze_logs(logs: list[dict[str, Any]], *, hours: int = 24) -> dict[str, Any]:
    """Analyse déterministe — réutilise la logique copilot."""
    from app.models.activity_log import ActivityLog

    rows = []
    for item in logs:
        row = ActivityLog(
            id=item.get("id") or 0,
            level=str(item.get("level") or "INFO"),
            category=str(item.get("category") or "system"),
            action=str(item.get("action") or ""),
            message=str(item.get("message") or ""),
        )
        row.created_at = item.get("created_at")
        rows.append(row)

    from app.services.ai_assistant.specialized_routes import _analyze_suspicious_logs_payload

    return _analyze_suspicious_logs_payload(rows, hours=hours)
