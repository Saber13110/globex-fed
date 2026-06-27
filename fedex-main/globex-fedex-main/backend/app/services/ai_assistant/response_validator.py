"""Validation anti-hallucination des réponses agent."""

from __future__ import annotations

import re
from typing import Any

_DATA_TRIGGERS = re.compile(
    r"\b(combien|how many|cuánt|cuant|nombre|total|liste|list|"
    r"statist|dernier|last|recent|aujourd|today|semaine|week|"
    r"tracking|colis|notification|utilisateur|user|ticket|log|"
    r"sécurité|security|conversation|mission|rapport|report|kpi|"
    r"actif|active|ouvert|open|unread|non lues?)\b",
    re.I,
)

_NUMBER_PATTERN = re.compile(
    r"\b(\d{1,6})\b(?:\s*(?:utilisateur|user|notification|ticket|colis|expédition|shipment|log|incident)s?)?",
    re.I,
)


def requires_tool_data(message: str) -> bool:
    return bool(_DATA_TRIGGERS.search(message or ""))


def validate_response(
    *,
    message: str,
    reply: str,
    tools_used: list[str],
    tool_payloads: list[dict[str, Any]],
) -> tuple[str, float, str | None]:
    """
    Valide la réponse. Retourne (reply_corrigée, confidence, warning).
    """
    if not (reply or "").strip():
        return (
            "Je n'ai pas pu produire de réponse. Réessayez ou précisez votre demande.",
            0.0,
            "empty_reply",
        )

    needs_data = requires_tool_data(message)
    if needs_data and not tools_used:
        warning = "missing_tools"
        reply = (
            f"{reply.strip()}\n\n"
            "_Note : cette question nécessite des données plateforme. "
            "Aucun outil n'a pu être consulté — vérifiez la connexion DB ou réessayez._"
        )
        return reply, 0.45, warning

    if needs_data and tools_used and not tool_payloads:
        return reply, 0.55, "empty_tool_payloads"

    confidence = 0.92 if tools_used and tool_payloads else 0.78
    if needs_data and tools_used:
        confidence = 0.94

    # Détecter chiffres sans outils
    if needs_data and not tools_used and _NUMBER_PATTERN.search(reply):
        return (
            reply + "\n\n_Ces chiffres n'ont pas été vérifiés via un outil backend._",
            0.35,
            "unverified_numbers",
        )

    return reply, confidence, None
