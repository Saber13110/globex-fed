"""Reformulation LLM + repli template pour e-mails utilisateur."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.admin_client.email.email_types import EmailScenario
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)

_META_RE = re.compile(
    r"\b(voici un e-mail|here is an email|objet\s*:|subject\s*:)\b",
    re.I,
)


def _factual_template(
    *,
    user_name: str,
    admin_note: str,
    scenario: EmailScenario,
    lang: str,
) -> str:
    name = user_name or "Client"
    note = (admin_note or "").strip()

    if scenario == EmailScenario.user_suspend:
        if lang == "en":
            intro = (
                "We are writing to inform you that your Globex FedEx account "
                "has been temporarily suspended."
            )
        else:
            intro = (
                "Nous vous informons que votre compte Globex FedEx "
                "a été temporairement suspendu."
            )
    elif scenario == EmailScenario.user_reactivate:
        if lang == "en":
            intro = "We are pleased to inform you that your Globex FedEx account has been reactivated."
        else:
            intro = "Nous avons le plaisir de vous informer que votre compte Globex FedEx a été réactivé."
    elif scenario == EmailScenario.ticket_reply:
        if lang == "en":
            intro = "We are writing to you regarding your support request on Globex FedEx."
        else:
            intro = "Nous vous contactons au sujet de votre demande support sur Globex FedEx."
    elif scenario == EmailScenario.ticket_resolved:
        if lang == "en":
            intro = "Your support ticket on Globex FedEx has been processed and marked as resolved."
        else:
            intro = "Votre ticket support Globex FedEx a été traité et marqué comme résolu."
    else:
        if lang == "en":
            intro = "We are writing to you regarding your Globex FedEx account."
        else:
            intro = "Nous vous contactons au sujet de votre compte Globex FedEx."

    if lang == "en":
        lines = [f"Hello {name},", "", intro]
        if note:
            lines.append(note)
        lines.extend(
            [
                "",
                "If you have any questions, please contact our support team.",
                "",
                "Best regards,",
                "The Globex FedEx Team",
            ]
        )
        return "\n".join(lines)

    lines = [f"Bonjour {name},", "", intro]
    if note:
        lines.append(note)
    lines.extend(
        [
            "",
            "Pour toute question, contactez notre équipe support.",
            "",
            "Cordialement,",
            "L'équipe Globex FedEx",
        ]
    )
    return "\n".join(lines)


def _validate_body(body: str, facts: dict[str, Any]) -> bool:
    if not body or _META_RE.search(body):
        return False
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 4 or len(lines) > 14:
        return False
    note = str(facts.get("admin_note") or "").strip()
    if note and note[:24].lower() not in body.lower():
        # au moins une trace du message admin
        note_words = [w for w in re.findall(r"\w{4,}", note.lower())[:6]]
        if note_words and not any(w in body.lower() for w in note_words[:3]):
            return False
    return True


def compose_user_email_body(
    facts: dict[str, Any],
    *,
    scenario: EmailScenario = EmailScenario.custom,
    lang: str = "fr",
) -> tuple[str, str | None]:
    """Retourne (body_text, llm_provider ou None)."""
    deterministic = _factual_template(
        user_name=str(facts.get("user_name") or ""),
        admin_note=str(facts.get("admin_note") or ""),
        scenario=scenario,
        lang=lang,
    )
    settings = get_settings()
    if not settings.llm_enabled:
        return deterministic, None

    facts_json = json.dumps(facts, ensure_ascii=False)[:2500]
    prompt_fr = (
        "Rédige un e-mail professionnel Globex FedEx à un utilisateur client.\n"
        "Règles STRICTES :\n"
        "- 8 à 10 lignes maximum (salutation + corps + formule de politesse)\n"
        "- Ton courtois, clair, sans jargon technique\n"
        "- Utilise UNIQUEMENT les faits JSON — n'invente rien\n"
        "- Pas de markdown, pas de titre « Objet », pas de liste à puces\n"
        "- Mentionne la raison / le message admin si présent dans admin_note\n"
    )
    prompt_en = (
        "Write a professional Globex FedEx email to a client user.\n"
        "STRICT rules:\n"
        "- 8 to 10 lines max (greeting + body + closing)\n"
        "- Courteous, clear tone, no technical jargon\n"
        "- Use ONLY JSON facts — do not invent anything\n"
        "- No markdown, no Subject line, no bullet lists\n"
    )
    system = (prompt_en if lang == "en" else prompt_fr) + "\n" + language_lock_instruction(lang)
    try:
        raw = call_ollama_session_summary(
            f"Faits:\n{facts_json}\n\nBrouillon de référence:\n{deterministic[:1200]}",
            session_title="Admin user email",
            ui_language=lang,
            system_prompt=system,
        )
        candidate = (raw or "").strip()
        if candidate and candidate != "RESUME_IMPOSSIBLE" and _validate_body(candidate, facts):
            return candidate, "ollama"
    except LlmProviderError:
        logger.debug("[admin_email] reformulation LLM indisponible", exc_info=True)
    return deterministic, None


def default_subject(*, scenario: EmailScenario, lang: str) -> str:
    subjects_fr = {
        EmailScenario.user_suspend: "Information importante — suspension de compte Globex FedEx",
        EmailScenario.user_reactivate: "Votre compte Globex FedEx a été réactivé",
        EmailScenario.ticket_reply: "Réponse à votre ticket support Globex FedEx",
        EmailScenario.ticket_resolved: "Votre ticket support Globex FedEx est résolu",
        EmailScenario.custom: "Information concernant votre compte Globex FedEx",
    }
    subjects_en = {
        EmailScenario.user_suspend: "Important — Globex FedEx account suspension",
        EmailScenario.user_reactivate: "Your Globex FedEx account has been reactivated",
        EmailScenario.ticket_reply: "Reply to your Globex FedEx support ticket",
        EmailScenario.ticket_resolved: "Your Globex FedEx support ticket is resolved",
        EmailScenario.custom: "Information regarding your Globex FedEx account",
    }
    table = subjects_en if lang == "en" else subjects_fr
    return table.get(scenario, table[EmailScenario.custom])
