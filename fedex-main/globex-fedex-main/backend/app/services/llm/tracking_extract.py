"""Extraction de numéros de suivi (regex)."""

from __future__ import annotations

from app.utils.tracking_parser import (
    extract_tracking_numbers,
    first_tracking_number,
    is_plausible_tracking_number,
)

__all__ = [
    "extract_all_tracking_numbers",
    "extract_tracking_number",
    "is_plausible_tracking_number",
]


def extract_tracking_number(message: str) -> str | None:
    """Détecte le premier numéro de suivi plausible dans le message."""
    return first_tracking_number(message)


def extract_all_tracking_numbers(message: str) -> list[str]:
    """Retourne tous les numéros plausibles détectés."""
    return list(extract_tracking_numbers(message))
