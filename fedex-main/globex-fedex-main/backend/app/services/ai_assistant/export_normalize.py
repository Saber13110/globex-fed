"""Normalisation des données avant export PDF/Excel — champs canoniques FR."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

EXPORT_DATA_ERROR = (
    "Impossible de générer le PDF : les données reçues sont vides ou mal mappées."
)


class ExportDataError(ValueError):
    """Données export invalides ou vides."""


_LIMIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:dernier|derniers|derni[eè]res?|dernieres)\s+(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,2})\s*(?:derni[eè]res?|derniers?|last|recentes?|r[eé]centes?)\b", re.I),
    re.compile(r"\b(?:premiers?|premi[eè]res?|premieres|first)\s+(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,2})\s*(?:premiers?|premi[eè]res?|premieres|first)\b", re.I),
    re.compile(r"\bjuste\s+les?\s+(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,2})\s+(?:users?|utilisateurs?|notifs?|notifications?|items?)\b", re.I),
]


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        val = raw.get(key)
        if val is not None and str(val).strip():
            return val
    return None


def _fmt_bool_read(val: Any) -> str:
    if val is True or str(val).lower() in {"true", "1", "lu", "read", "yes", "oui"}:
        return "Lu"
    if val is False or str(val).lower() in {"false", "0", "non lu", "unread", "no", "non"}:
        return "Non lu"
    return str(val) if val is not None else "-"


def parse_export_limit(message: str, *, default: int | None = None) -> int | None:
    """Extrait une limite depuis le message (« 3 derniers », « 6 premiers », « juste les 6 »)."""
    text = (message or "").strip()
    for pattern in _LIMIT_PATTERNS:
        m = pattern.search(text)
        if m:
            return min(max(int(m.group(1)), 1), 50)
    return default


def apply_export_limit(
    items: list[dict[str, Any]],
    *,
    limit: int | None,
    contextual: bool = False,
    state_limit: int | None = None,
) -> list[dict[str, Any]]:
    """Applique la limite demandée AVANT génération PDF."""
    if not items:
        return []
    effective = limit
    if contextual and state_limit and not limit:
        effective = state_limit
    if effective is None:
        return list(items)
    return list(items[: min(max(int(effective), 1), len(items))])


def normalize_user_for_export(raw: dict[str, Any]) -> dict[str, str]:
    name = _pick(raw, "nom", "full_name", "name", "fullName", "user_name")
    if not name and raw.get("email"):
        name = str(raw["email"]).split("@")[0]
    return {
        "nom": str(name or "-"),
        "email": str(_pick(raw, "email", "user_email", "mail") or "-"),
        "role": str(_pick(raw, "role", "user_role", "rôle") or "-"),
        "statut": str(_pick(raw, "statut", "status") or "-"),
        "id": str(_pick(raw, "id", "user_id") or "-"),
    }


def normalize_notification_for_export(raw: dict[str, Any]) -> dict[str, str]:
    is_read = raw.get("is_read", raw.get("lu", raw.get("read")))
    return {
        "titre": str(_pick(raw, "titre", "title", "subject", "name") or "-"),
        "message": str(_pick(raw, "message", "body", "content", "text") or "-")[:300],
        "type": str(_pick(raw, "type", "category", "categorie", "kind") or "-"),
        "priorite": str(_pick(raw, "priorite", "priority", "level") or "-"),
        "date": str(_pick(raw, "date", "created_at", "time_label", "timestamp") or "-")[:19],
        "lu": _fmt_bool_read(is_read),
    }


def normalize_tracking_for_export(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "numero": str(_pick(raw, "numero", "tracking_number", "trackingNumber", "tn") or "-"),
        "statut": str(_pick(raw, "statut", "status", "status_description") or "-"),
        "utilisateur": str(_pick(raw, "utilisateur", "user_name", "user_label", "full_name") or "-"),
        "email": str(_pick(raw, "email", "user_email") or "-"),
        "date": str(_pick(raw, "date", "created_at", "updated_at") or "-")[:19],
    }


def normalize_log_for_export(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "date": str(_pick(raw, "date", "created_at", "timestamp") or "-")[:19],
        "niveau": str(_pick(raw, "niveau", "level", "severity") or "-"),
        "action": str(_pick(raw, "action", "event", "type") or "-"),
        "message": str(_pick(raw, "message", "detail", "description") or "-")[:250],
    }


def normalize_ticket_for_export(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(_pick(raw, "id", "ticket_id") or "-"),
        "sujet": str(_pick(raw, "sujet", "subject", "title") or "-"),
        "statut": str(_pick(raw, "statut", "status") or "-"),
        "priorite": str(_pick(raw, "priorite", "priority") or "-"),
        "utilisateur": str(_pick(raw, "utilisateur", "user_name", "requester") or "-"),
    }


_NORMALIZERS = {
    "users": normalize_user_for_export,
    "notifications": normalize_notification_for_export,
    "tracking": normalize_tracking_for_export,
    "logs": normalize_log_for_export,
    "tickets": normalize_ticket_for_export,
}


def normalize_items_for_export(
    items: list[dict[str, Any]],
    module: str,
) -> list[dict[str, str]]:
    normalizer = _NORMALIZERS.get(module)
    if not normalizer:
        return [
            {str(k): str(v) for k, v in row.items() if v is not None}
            for row in items
            if isinstance(row, dict)
        ]
    return [normalizer(row) for row in items if isinstance(row, dict)]


def _row_has_content(row: dict[str, str]) -> bool:
    for val in row.values():
        if val and str(val).strip() not in {"-", ""}:
            return True
    return False


def validate_export_dataset(items: list[dict[str, Any]], module: str) -> list[dict[str, str]]:
    """Valide et normalise — lève ExportDataError si vide."""
    if not items:
        raise ExportDataError("Impossible de générer le PDF : aucune donnée à exporter.")
    normalized = normalize_items_for_export(items, module)
    if not normalized or not any(_row_has_content(row) for row in normalized):
        raise ExportDataError(EXPORT_DATA_ERROR)
    return normalized


def resolve_export_limit_for_turn(
    message: str,
    *,
    items_count: int,
    contextual: bool,
    state_limit: int | None,
    explicit_limit: int | None = None,
) -> int:
    """Limite finale pour l'export."""
    from_message = explicit_limit or parse_export_limit(message)
    if contextual:
        if from_message:
            return min(from_message, items_count)
        if state_limit:
            return min(state_limit, items_count)
        return items_count
    if from_message:
        return from_message
    if state_limit:
        return min(state_limit, items_count)
    return items_count
