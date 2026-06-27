"""Profil de préférences structuré (ton / style) — composition texte pour le LLM."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.preference_profile import PreferenceProfileStructured

ALLOWED_TONES = frozenset({"professional", "friendly", "concise", "formal"})


def _normalize_tone(value: str | None) -> str:
    raw = (value or "professional").strip().lower()
    return raw if raw in ALLOWED_TONES else "professional"


def profile_from_payload(data: dict[str, Any] | PreferenceProfileStructured | None) -> PreferenceProfileStructured:
    if isinstance(data, PreferenceProfileStructured):
        return data
    if not data:
        return PreferenceProfileStructured()
    return PreferenceProfileStructured(
        tone=_normalize_tone(data.get("tone")),
        cite_fedex=bool(data.get("cite_fedex", True)),
        short_answers=bool(data.get("short_answers", False)),
        free_notes=str(data.get("free_notes") or "")[:300],
    )


def profile_to_json(profile: PreferenceProfileStructured) -> str:
    return json.dumps(profile.model_dump(), ensure_ascii=False)


def profile_from_json(raw: str | None) -> PreferenceProfileStructured | None:
    if not (raw or "").strip():
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return profile_from_payload(data)
    except json.JSONDecodeError:
        pass
    return None


_TONE_LABELS = {
    "professional": "Ton professionnel et courtois",
    "friendly": "Ton amical et accessible",
    "concise": "Réponses courtes et directes",
    "formal": "Ton formel et soutenu",
}


def compose_preference_text(profile: PreferenceProfileStructured) -> str:
    """Construit un texte de style sûr (pas d'instructions système)."""
    lines = [_TONE_LABELS.get(profile.tone, _TONE_LABELS["professional"])]
    if profile.cite_fedex:
        lines.append("Mentionner FedEx lorsque c'est pertinent pour le suivi ou la logistique.")
    if profile.short_answers:
        lines.append("Réponses concises : aller à l'essentiel en 2–4 phrases.")
    else:
        lines.append(
            "Réponses structurées et professionnelles (style assistant produit premium) : "
            "réponse directe d'abord, paragraphes courts, proposition de suite seulement si utile."
        )
    notes = profile.free_notes.strip()
    if notes:
        lines.append(f"Précision utilisateur (style uniquement) : {notes}")
    return "\n".join(lines)
