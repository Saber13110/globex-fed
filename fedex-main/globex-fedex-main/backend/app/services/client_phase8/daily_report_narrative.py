"""Synthèse exécutive Ollama + repli factuel pour le rapport quotidien."""

from __future__ import annotations

import logging

from app.services.client_phase4.session_summary_validator import is_acceptable_summary
from app.services.client_phase8.daily_report_collector import DailyReportSnapshot
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)

_PROMPT_FR = """Tu rédiges la synthèse exécutive d'un rapport d'activité quotidien FedEx Globex.
Règles STRICTES :
- 5 à 6 phrases professionnelles, ton courtois
- Utilise UNIQUEMENT les faits fournis (KPI, alertes) — n'invente rien
- Mentionne les notifications non lues et alertes importantes si présentes
- Pas de listes à puces, pas de markdown, pas de titre
"""

_PROMPT_EN = """You write the executive summary of a FedEx Globex daily activity report.
STRICT rules:
- 5 to 6 professional sentences, courteous tone
- Use ONLY the provided facts (KPIs, alerts) — do not invent anything
- Mention unread and important alerts when present
- No bullet lists, no markdown, no title
"""


def _factual_fallback(snapshot: DailyReportSnapshot) -> str:
    lang = snapshot.lang
    k = snapshot.kpi_dict()
    if lang == "en":
        parts = [
            f"Today you sent {k['messages']} chat message(s) and tracked {k['trackings']} shipment(s).",
            f"You generated {k['exports']} export(s) and activated {k['watches']} watch(es).",
            f"You have {k['unread_notifications']} unread notification(s) on your account.",
        ]
        if snapshot.important_notifications:
            parts.append(
                f"{len(snapshot.important_notifications)} important alert(s) require your attention."
            )
        if k["unread_notifications"] == 0 and not snapshot.important_notifications:
            parts.append("Your notification inbox has no pending urgent items.")
        return " ".join(parts[:6])

    parts = [
        f"Aujourd'hui vous avez envoyé {k['messages']} message(s) chat et consulté {k['trackings']} colis.",
        f"Vous avez généré {k['exports']} export(s) et activé {k['watches']} surveillance(s).",
        f"Vous avez {k['unread_notifications']} notification(s) non lue(s) sur votre compte.",
    ]
    if snapshot.important_notifications:
        parts.append(
            f"{len(snapshot.important_notifications)} alerte(s) importante(s) méritent votre attention."
        )
    if k["unread_notifications"] == 0 and not snapshot.important_notifications:
        parts.append("Votre boîte de notifications ne contient pas d'élément urgent en attente.")
    return " ".join(parts[:6])


def factual_daily_report_narrative(snapshot: DailyReportSnapshot) -> str:
    """Synthèse déterministe sans LLM."""
    return _factual_fallback(snapshot)


def generate_daily_report_narrative(snapshot: DailyReportSnapshot) -> str:
    transcript = snapshot.facts_transcript()
    lang = snapshot.lang
    base = _PROMPT_EN if lang == "en" else _PROMPT_FR
    system = f"{base}\n{language_lock_instruction(lang)}"
    title = "Rapport quotidien" if lang != "en" else "Daily report"
    try:
        raw = call_ollama_session_summary(
            transcript,
            session_title=title,
            ui_language=lang,
            system_prompt=system,
        )
        candidate = (raw or "").strip()
        if candidate and is_acceptable_summary(candidate, transcript, session_title=title):
            return candidate
    except LlmProviderError:
        logger.warning("daily report narrative Ollama failed, factual fallback", exc_info=True)
    return factual_daily_report_narrative(snapshot)
