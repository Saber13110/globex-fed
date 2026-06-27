"""Cerveau Gemini pour missions agent admin."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)

ADMIN_AGENT_BRAIN_PROMPT = """Tu n'es PAS un chatbot qui répond seulement aux questions.
Tu es un agent capable de raisonner et d'exécuter des tâches pour l'administrateur Globex FedEx.
Tu ne inventes JAMAIS de résultat.

PROCESSUS OBLIGATOIRE :
1. OBJECTIF — Identifier ce que l'admin veut vraiment obtenir.
2. PLAN — Créer un plan court de 2 à 5 étapes.
3. ACTION — Choisir l'action la plus logique (action_tool) parmi les outils disponibles.
4. VÉRIFICATION — Définir comment contrôler que le résultat répond à la demande.

OUTILS ADMIN (action_tool) :
- export_and_email_tracking : Excel des numéros de colis + envoi e-mail (tracking_numbers[], email_to)
- export_tracking_excel : Excel seulement
- suspend_user / reactivate_user : compte utilisateur (un seul)
- reactivate_all_suspended : réactiver tous les comptes suspendus (max selon mission)
- reply_support_ticket : répondre à un ticket client (ticket_id, reply_body ou consignes)
- export_activity_logs_pdf : télécharger les logs d'activité en PDF (période en heures dans la tâche, ex. 2h)
- export_activity_logs_excel : télécharger les logs en Excel (colonnes Date, Titre, Type de log)
- daily_behavior_report : rapport comportement utilisateurs (analyse)
- analyze_tracking / analyze_tickets / analyze_notifications / analyze_logs / generate_summary : analyse seule
- analyze_users : analyse comptes sans action destructive

RÈGLES :
- Ne jamais prétendre qu'une action est faite si tu n'as pas l'outil adapté.
- Chaque fait cité doit référencer les données fournies (user_id, action, horodatage).
- Si paramètres manquants (email, numéros colis) : needs_clarification=true, UNE question, ready_to_execute=false.
- Si la tâche est simple et complète (ex. PDF logs 2h) : ready_to_execute=true, needs_clarification=false.
- Action sensible (mail tiers, suspend) : note dans verification.

Réponds UNIQUEMENT en JSON :
{
  "objective": "...",
  "plan": ["étape 1", "étape 2"],
  "action_tool": "identifiant",
  "verification": "critère de succès mesurable",
  "parameters": { "tracking_numbers": [], "email_to": "", "user_hint": "", "ticket_id": 0, "reply_hint": "" },
  "assistant_intro": "phrase naturelle montrant la compréhension",
  "ready_to_execute": true,
  "needs_clarification": false,
  "clarification_question": ""
}"""


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def plan_admin_mission(
    task: str,
    *,
    agent_type: str,
    context_summary: str = "",
    ui_language: str = "fr",
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        from app.services.llm.providers import _gemini_generate

        lang = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
        prompt = (
            f"{lang}\n\n{ADMIN_AGENT_BRAIN_PROMPT}\n\n"
            f"AGENT MISSION TYPE: {agent_type}\n"
            f"TÂCHE ADMIN:\n{task}\n\n"
            f"DONNÉES CONTEXTE (résumé):\n{context_summary[:6000]}"
        )
        raw = _gemini_generate(prompt, max_output_tokens=800, ui_language=ui_language)
        return _parse_json_object(raw)
    except Exception:
        logger.warning("plan_admin_mission failed", exc_info=True)
        return None


def synthesize_mission_reply(
    *,
    task: str,
    tool: str,
    technical_result: str,
    steps_summary: str = "",
    ui_language: str = "fr",
) -> str | None:
    settings = get_settings()
    if not settings.llm_enabled or not technical_result.strip():
        return None
    try:
        from app.services.llm.providers import _gemini_generate

        lang = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
        from app.services.gpt.writing_style import professional_writing_for_lang

        prompt = (
            f"{lang}\n\n{professional_writing_for_lang(ui_language)}\n\n"
            "Vous êtes l'agent admin Globex FedEx. Reformulez le RÉSULTAT RÉEL pour l'administrateur.\n"
            "Ouvrez par l'état : **Fait** / **Non fait** / **En attente** selon le cas.\n"
            "Citez des faits concrets (e-mails, numéros, statuts). Ne jamais inventer.\n"
            "Clôturez par 1–2 actions suggérées, en prose courte.\n\n"
            f"Tâche : {task[:500]}\nOutil : {tool}\nRésultat technique :\n{technical_result[:3000]}\n"
        )
        if steps_summary:
            prompt += f"\nÉtapes:\n{steps_summary[:1000]}\n"
        prompt += "\nRéponse pour l'admin:"
        return _gemini_generate(prompt, max_output_tokens=900, ui_language=ui_language).strip()
    except Exception:
        logger.warning("synthesize_mission_reply failed", exc_info=True)
        return None


def draft_support_reply(
    task: str,
    ticket_ctx: dict[str, Any],
    *,
    reply_hint: str = "",
    ui_language: str = "fr",
) -> str:
    """Rédige un brouillon de réponse support à partir du fil ticket."""
    settings = get_settings()
    if not settings.llm_enabled:
        return (
            f"Bonjour,\n\nNous avons bien reçu votre demande concernant « {ticket_ctx.get('subject', '')} ». "
            "Notre équipe traite votre dossier.\n\nCordialement,\nSupport Globex FedEx"
        )
    try:
        from app.services.llm.providers import _gemini_generate

        lang = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
        ctx_json = json.dumps(ticket_ctx, ensure_ascii=False, default=str)[:5000]
        prompt = (
            f"{lang}\n\n"
            "Tu rédiges la réponse OFFICIELLE du support admin Globex FedEx au client.\n"
            "Ton : professionnel, empathique, concis. En français.\n"
            "Base-toi UNIQUEMENT sur le fil du ticket. Ne promets rien d'impossible.\n"
            "Pas de markdown. Pas de signature longue — termine par « Support Globex FedEx ».\n\n"
            f"CONSIGNE ADMIN:\n{task[:800]}\n"
        )
        if reply_hint.strip():
            prompt += f"\nINDICATIONS RÉPONSE:\n{reply_hint[:500]}\n"
        prompt += f"\nTICKET (JSON):\n{ctx_json}\n\nRédige la réponse au client:"
        return _gemini_generate(prompt, max_output_tokens=700, ui_language=ui_language).strip()
    except Exception:
        logger.warning("draft_support_reply failed", exc_info=True)
        return (
            f"Bonjour,\n\nMerci pour votre message concernant « {ticket_ctx.get('subject', '')} ». "
            "Nous revenons vers vous rapidement.\n\nSupport Globex FedEx"
        )


ADMIN_ANALYST_PROMPT = (
    "Vous êtes analyste opérations / sécurité Globex FedEx pour l'administrateur.\n"
    "Vous recevez des FAITS AGRÉGÉS (JSON) — journaux, scores risque, tickets.\n"
    "Rédigez un rapport sobre et actionnable en français :\n"
    "- **Synthèse** (2–3 phrases)\n"
    "- **Alertes prioritaires** (puces courtes, user_id + email + raison)\n"
    "- **Faits marquants**\n"
    "- **Recommandations** (1–3 actions concrètes)\n"
    "Ne jamais inventer d'événement absent des données. Pas de mur de texte."
)


def analyze_with_facts(task: str, facts: dict[str, Any], *, ui_language: str = "fr") -> tuple[str, bool]:
    settings = get_settings()
    if not settings.llm_enabled:
        return _fallback_analyst_text(task, facts), True
    try:
        from app.services.llm.providers import _gemini_generate

        facts_json = json.dumps(facts, ensure_ascii=False, default=str)[:12000]
        prompt = (
            f"TÂCHE: {task}\n\nFAITS (JSON):\n{facts_json}\n\n"
            "Rapport analyste (citations obligatoires pour les users à risque):"
        )
        return _gemini_generate(
            prompt,
            max_output_tokens=1200,
            system_instruction=ADMIN_ANALYST_PROMPT,
            ui_language=ui_language,
        ).strip(), False
    except Exception:
        logger.warning("analyze_with_facts failed", exc_info=True)
        return _fallback_analyst_text(task, facts), True


def _fallback_analyst_text(task: str, facts: dict[str, Any]) -> str:
    behavior = facts.get("behavior") if isinstance(facts.get("behavior"), dict) else facts
    flags = (behavior.get("risk_flags") if isinstance(behavior, dict) else None) or facts.get("risk_flags") or []
    period = behavior.get("period_hours") if isinstance(behavior, dict) else facts.get("period_hours", 24)
    logs_total = behavior.get("logs_total") if isinstance(behavior, dict) else facts.get("logs_total", 0)
    lines = [
        "⚠️ Gemini indisponible — synthèse locale uniquement (pas d'invention de données).",
        f"Tâche : {task[:120]}",
        "",
        f"Logs sur {period}h : {logs_total}",
    ]
    if flags:
        lines.append("Utilisateurs à surveiller :")
        for f in flags[:5]:
            lines.append(f"- {f.get('email') or f.get('user_id')} : {', '.join(f.get('reasons') or [])}")
    else:
        lines.append("Aucun profil à risque détecté sur la période.")
    return "\n".join(lines)
