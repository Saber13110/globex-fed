"""Moteur de raisonnement entreprise — synthèse multi-outils + format exécutif."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.services.ai_assistant.llm_router import LlmSynthesisResult, synthesize_with_router

logger = logging.getLogger(__name__)

_ENTERPRISE_STRUCTURE = """
STRUCTURE OBLIGATOIRE de ta réponse (markdown) :

## Résumé exécutif
(2-3 phrases claires pour un admin)

## Données vérifiées
(liste factuelle issue UNIQUEMENT des outils — chiffres, statuts, IDs)

## Analyse IA
(retard ? anomalie ? impact utilisateur ? ticket associé ? tendances ?)

## Risques
(faible / moyen / élevé + justification courte)

## Recommandations
(1-3 actions concrètes pour l'administrateur)

---
Confiance : XX %
"""

_CRITICAL_PLAN: list[tuple[str, dict[str, Any]]] = [
    ("get_security_alerts", {"status": "open", "limit": 15}),
    ("get_recent_logs", {"hours": 24, "limit": 30}),
    ("get_open_tickets", {"status": "open", "limit": 20}),
    ("get_notifications_summary", {"limit": 15, "critical_only": True}),
]

_CRITICAL_PATTERN = __import__("re").compile(
    r"\b(probl[eè]mes?\s+critiques?|critical\s+issues?|priorit[eé]s?\s+aujourd|"
    r"urgences?|what.{0,20}critical|quoi.{0,20}critique)\b",
    __import__("re").I,
)


@dataclass
class EnterpriseSynthesis:
    reply: str
    mode: str
    confidence: float
    reasoning_summary: str
    tools_used: list[str]
    verified_data: str | None = None
    risks: str | None = None
    recommendations: str | None = None


def is_critical_executive_question(message: str) -> bool:
    return bool(_CRITICAL_PATTERN.search(message or ""))


def plan_critical_tools() -> list[tuple[str, dict[str, Any]]]:
    return list(_CRITICAL_PLAN)


def build_verified_data_block(tool_payloads: list[dict[str, Any]]) -> str:
    """Extrait les faits vérifiables des payloads outils."""
    lines: list[str] = []
    for item in tool_payloads:
        name = item.get("name", "?")
        resp = item.get("response") or {}
        if resp.get("status") == "error":
            lines.append(f"- **{name}** : erreur — {resp.get('error', '?')}")
            continue
        data = {k: v for k, v in resp.items() if k not in {"status", "error"}}
        if not data:
            continue
        snippet = json.dumps(data, ensure_ascii=False, default=str)[:600]
        lines.append(f"- **{name}** : {snippet}")
    return "\n".join(lines[:8]) if lines else "Aucune donnée outil disponible."


def _build_synthesis_task(
    message: str,
    tool_payloads: list[dict[str, Any]],
    *,
    lang: str,
    entity_context: str = "",
) -> str:
    verified = build_verified_data_block(tool_payloads)
    lang_rule = (
        "Réponds UNIQUEMENT en français."
        if lang == "fr"
        else f"Reply ONLY in {lang}."
    )
    parts = [
        f"QUESTION ADMIN : {message}",
        lang_rule,
        _ENTERPRISE_STRUCTURE,
        "DONNÉES VÉRIFIÉES (ne jamais inventer au-delà) :",
        verified,
    ]
    if entity_context:
        parts.insert(1, entity_context)
    return "\n\n".join(parts)


def _structured_fallback(
    message: str,
    tool_payloads: list[dict[str, Any]],
    *,
    lang: str,
) -> EnterpriseSynthesis:
    """Repli structuré si LLM indisponible — format entreprise minimal."""
    verified = build_verified_data_block(tool_payloads)
    tools = [p.get("name", "") for p in tool_payloads if p.get("name")]

    if lang == "en":
        reply = (
            "## Executive summary\n"
            f"Analysis based on {len(tools)} verified tool(s) for your question.\n\n"
            "## Verified data\n"
            f"{verified}\n\n"
            "## AI analysis\n"
            "Structured synthesis unavailable — LLM engine temporarily unreachable.\n\n"
            "## Risks\n"
            "Medium — manual review recommended.\n\n"
            "## Recommendations\n"
            "- Review verified data above.\n"
            "- Retry in a few seconds for full AI synthesis.\n\n"
            "---\nConfidence: 72 %"
        )
    else:
        reply = (
            "## Résumé exécutif\n"
            f"Analyse basée sur {len(tools)} outil(s) vérifié(s) pour votre question.\n\n"
            "## Données vérifiées\n"
            f"{verified}\n\n"
            "## Analyse IA\n"
            "Synthèse structurée indisponible — moteur LLM momentanément injoignable.\n\n"
            "## Risques\n"
            "Moyen — revue manuelle recommandée.\n\n"
            "## Recommandations\n"
            "- Examiner les données vérifiées ci-dessus.\n"
            "- Réessayer dans quelques secondes pour une synthèse IA complète.\n\n"
            "---\nConfiance : 72 %"
        )

    return EnterpriseSynthesis(
        reply=reply,
        mode="local_fallback",
        confidence=0.72,
        reasoning_summary=f"Repli structuré — outils : {', '.join(tools)}.",
        tools_used=tools,
        verified_data=verified,
    )


def synthesize_enterprise_response(
    message: str,
    tool_payloads: list[dict[str, Any]],
    *,
    lang: str = "fr",
    entity_context: str = "",
    prefer_pro: bool = False,
) -> EnterpriseSynthesis:
    """
    Tool Output + Gemini (Flash → Pro → Ollama → fallback structuré).
    """
    if not tool_payloads:
        return EnterpriseSynthesis(
            reply="Je n'ai pas de données vérifiées pour répondre.",
            mode="local_fallback",
            confidence=0.3,
            reasoning_summary="Aucun outil exécuté.",
            tools_used=[],
        )

    tools = [p.get("name", "") for p in tool_payloads if p.get("name")]
    task = _build_synthesis_task(message, tool_payloads, lang=lang, entity_context=entity_context)

    from app.services.gpt.prompts import admin_gpt_system_for_lang

    system = admin_gpt_system_for_lang(lang)
    system += "\n\nTu es un copilote admin FedEx Globex niveau entreprise. Analyse, ne liste pas."

    result: LlmSynthesisResult = synthesize_with_router(
        task=message,
        system_instruction=system,
        user_payload=task,
        tool_declarations=[],
        on_tool_call=lambda *_: {},
        tool_payloads=tool_payloads,
        ui_language=lang,
        prefer_pro=prefer_pro,
        tools_already_executed=True,
    )

    if result.reply and result.mode in {"jarvis", "ollama", "gemini", "gemini_pro"}:
        confidence = (
            0.92 if result.mode in {"gemini", "jarvis"}
            else 0.88 if result.mode == "gemini_pro"
            else 0.82
        )
        if "Confiance" not in result.reply and "Confidence" not in result.reply:
            result.reply += f"\n\n---\nConfiance : {int(confidence * 100)} %"
        return EnterpriseSynthesis(
            reply=result.reply,
            mode=result.mode,
            confidence=confidence,
            reasoning_summary=f"Synthèse {result.mode} — outils : {', '.join(tools)}.",
            tools_used=tools,
            verified_data=build_verified_data_block(tool_payloads),
        )

    fallback = _structured_fallback(message, tool_payloads, lang=lang)
    logger.info("[Reasoning] structured fallback — mode=%s", fallback.mode)
    return fallback


def enrich_response_dict(
    response: dict[str, Any],
    synthesis: EnterpriseSynthesis,
    *,
    entity_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enrichit une réponse copilot avec le format entreprise."""
    response["reply"] = synthesis.reply
    response["answer"] = synthesis.reply
    response["mode"] = synthesis.mode
    response["llm_provider"] = synthesis.mode
    response["llm_degraded"] = synthesis.mode == "local_fallback"
    response["confidence"] = synthesis.confidence
    response["reasoning_summary"] = synthesis.reasoning_summary
    response["tools_used"] = synthesis.tools_used
    response["verified_data"] = synthesis.verified_data
    if entity_state:
        response["copilot_state"] = entity_state
    response["agent_reasoning"] = {
        "objective": response.get("intent", "analysis"),
        "plan": [f"Outil : {t}" for t in synthesis.tools_used],
        "synthesis_mode": synthesis.mode,
    }
    return response
