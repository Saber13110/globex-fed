"""Copilot admin — chat avec exécution réelle (runtime Agent Missions).

Pipeline nominal (toute reformulation utilisateur)::

    Question admin
        → Prompt Guard (blocage strict injection)
        → Préférence langue (relance « réponds en français »)
        → Export contextuel UNIQUEMENT si format explicite + contexte (pas « donne-moi »)
        → Gemini (comprend, choisit outils, raisonne)
        → READ TOOLS → payloads JSON uniquement
        → Synthèse Gemini OBLIGATOIRE après tout tools_used
        → Réponse française affichée (llm_provider=gemini)

Repli dégradé (Gemini indisponible : quota, timeout, surcharge)::

        → Routes emergency déterministes (intent hint + exécution outil)
        → Payload JSON réel → synthesize_copilot_reply (Gemini si possible)
        → Sinon degraded_format_tool_payload (llm_provider=degraded)

Règles invariantes::

    - PDF/Excel = format d'export, jamais module « logs » par défaut.
    - « donne / montre / liste » → Gemini + outil lecture, jamais export direct.
    - Salutations → Gemini (pas de template regex dans le pipeline).
    - intent_classifier = indice non contraignant injecté dans le contexte Gemini.
    - Aucun formatter (_format_tool) sur le chemin nominal.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent_approval_request import AgentApprovalRequest
from app.models.agent_mission import AgentMission
from app.models.agent_mission_step import AgentMissionStep
from app.models.user import User
from app.services.admin_agent_runtime import execute_admin_mission_task
from app.services.agent_mission_service import (
    AGENT_LABELS,
    AGENT_ROLE_META,
    _enrich_mission_context,
    _gather_mission_context,
    _handle_step_output,
)
from app.services.admin_logs_export_service import parse_log_period_hours
from app.services.shipment_pdf_service import build_tracking_status_export_download
from app.services.command_center_service import build_command_center
from app.services.gpt.intent_classifier import (
    INTENT_ADMIN_AGENTS,
    INTENT_ADMIN_CONVERSATIONS,
    INTENT_ADMIN_LOGS,
    INTENT_ADMIN_NOTIFICATIONS,
    INTENT_ADMIN_QUERY,
    INTENT_ADMIN_TICKETS,
    INTENT_ADMIN_TRACKING,
    INTENT_ADMIN_USERS,
    INTENT_CAPABILITIES,
    INTENT_KNOWLEDGE,
    INTENT_SECURITY,
    classify_intent,
)
from app.services.gpt.model_gateway import generate_ollama_admin_fast, generate_with_context
from app.services.gpt.orchestrator import SLUG_ADMIN, load_gpt_by_slug, run_gpt_turn
from app.services.gpt.prompt_composer import build_gpt_user_payload
from app.services.gpt.tool_handlers import HANDLERS
from app.services.gpt.tool_types import ToolExecutionContext
from app.services.llm.prompts import prompt_injection_refusal
from app.services.llm.providers import normalize_lang_code, gemini_api_key_usable
from app.services.llm.gemini_budget import is_global_gemini_quota_exhausted
from app.services.prompt_guard_service import assess_user_message, must_block_preferences
from app.utils.tracking_parser import extract_tracking_numbers

import logging

logger = logging.getLogger(__name__)


def _admin_copilot_uses_jarvis() -> bool:
    """Cerveau admin intégré : Ollama llama3.2:3b (Jarvis) — pas Gemini."""
    return (get_settings().llm_primary_provider or "ollama").lower() == "ollama"

QUICK_ACTION_TASKS: dict[str, tuple[str, str]] = {
    "delays": (
        "tracking",
        "Analyse les expéditions en retard et liste les colis concernés avec recommandations.",
    ),
    "exceptions": (
        "notifications",
        "Liste les principales exceptions et incidents sécurité ouverts aujourd'hui.",
    ),
    "report": (
        "summary",
        "Génère un rapport opérationnel 24h : comportements utilisateurs, alertes et KPIs.",
    ),
    "activity": (
        "logs",
        "Analyse les journaux d'activité des dernières 24h et signale les anomalies.",
    ),
    "countries": (
        "tracking",
        "Analyse les performances de livraison par région à partir des expéditions en base.",
    ),
    "predict": (
        "summary",
        "Prédit les retards probables demain à partir des expéditions et logs récents.",
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def format_copilot_history(messages: list[dict[str, str]] | None) -> str:
    """Formate l'historique UI admin pour le bloc CONVERSATION_HISTORY."""
    if not messages:
        return ""
    lines: list[str] = []
    for item in messages[-12:]:
        role = (item.get("role") or "user").lower()
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 800:
            content = content[:800] + "…"
        label = "Administrateur" if role in {"user", "admin"} else "Copilot"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def resolve_copilot_message(message: str, quick_action: str | None = None) -> str:
    text = (message or "").strip()
    quick = (quick_action or "").strip().lower()
    if quick and quick in QUICK_ACTION_TASKS:
        return QUICK_ACTION_TASKS[quick][1]
    return text


def detect_copilot_agent_type(message: str, quick_action: str | None = None) -> str:
    quick = (quick_action or "").strip().lower()
    if quick in QUICK_ACTION_TASKS:
        return QUICK_ACTION_TASKS[quick][0]

    task_l = (message or "").lower()
    best_agent = "summary"
    best_score = 0
    for atype, meta in AGENT_ROLE_META.items():
        score = sum(1 for kw in meta["keywords"] if kw in task_l)
        if score > best_score:
            best_score = score
            best_agent = atype
    return best_agent


def _enrich_task_with_attachment(task: str, attached_document_name: str | None) -> str:
    """Conserve le message utilisateur tel quel — l'indice fichier passe par SERVER_INSTRUCTION."""
    return (task or "").strip() or (
        f"Analyse le fichier « {attached_document_name} » et fournis les informations demandées."
        if attached_document_name
        else ""
    )


_FR_MESSAGE_WORDS = re.compile(
    r"\b(bonjour|salut|merci|coucou|bonsoir|svp|veux|voudrais|donne|liste|affiche|"
    r"journaux|utilisateurs|colis|tickets|notifications|conversations|qu'?est|"
    r"peux|pouvez|comment|pourquoi|combien|français|francais)\b",
    re.I,
)
_EN_MESSAGE_WORDS = re.compile(
    r"\b(hello|hi|thanks|please|show|give|list|users|logs|tickets|what can|how can)\b",
    re.I,
)


def _detect_message_language(message: str) -> str | None:
    """Langue dominante du message utilisateur (prioritaire sur le profil)."""
    from app.services.ai_assistant.language_service import detect_message_language

    text = (message or "").strip()
    if not text:
        return None
    return detect_message_language(text)


def _resolve_copilot_language(
    admin: User,
    message: str,
    *,
    session_language: str | None = None,
) -> str:
    """Langue de réponse : préférence explicite > session > détection > profil > fr."""
    from app.services.ai_assistant.language_service import resolve_response_language

    lang, _ = resolve_response_language(
        message,
        profile_language=admin.preferred_language,
        session_language=session_language,
    )
    return lang


def _greeting_reply_text(*, lang: str, agent_mode: bool = False, message: str = "") -> str:
    if lang == "en":
        mode = "Agent" if agent_mode else "Analysis"
        low = (message or "").lower().strip()
        if re.match(r"^good\s+evening", low):
            salutation = "Good evening"
        elif re.match(r"^hi\b", low):
            salutation = "Hi"
        else:
            salutation = "Hello"
        return (
            f"{salutation}! I'm your **Globex FedEx Super Admin copilot**.\n\n"
            f"Current mode: **{mode}** — tracking, users, tickets, logs, "
            "notifications, and KPI summaries.\n\n"
            "What would you like to check?"
        )
    if lang == "ar":
        return (
            "مرحباً! أنا **مساعد Globex FedEx للمشرف الأعلى**.\n\n"
            "كيف يمكنني مساعدتك اليوم؟"
        )
    mode_line = (
        "Mode actuel : **Agent** — j'exécute les actions avec approbation si nécessaire."
        if agent_mode
        else "Mode actuel : **Analyse** — je consulte les données et conseille."
    )
    low = (message or "").lower().strip()
    if re.match(r"^bonsoir", low):
        salutation = "Bonsoir"
        closing = "Que souhaitez-vous vérifier ce soir ?"
    elif re.match(r"^(salut|coucou)", low):
        salutation = "Salut"
        closing = "Comment puis-je vous aider ?"
    else:
        salutation = "Bonjour"
        closing = "Que souhaitez-vous faire ?"
    return (
        f"{salutation} ! Je suis **Jarvis**, assistant Super Admin Globex FedEx.\n\n"
        "Suivi des expéditions, utilisateurs, tickets, journaux, notifications et synthèses KPI.\n\n"
        f"{mode_line}\n\n"
        f"{closing}"
    )


def _is_greeting_message(message: str) -> bool:
    return bool(
        re.match(
            r"^(bonjour|salut|coucou|bonsoir|hello|hi|hey|good\s+evening|merci|thanks)[\s!.?]*$",
            (message or "").lower().strip(),
        )
    )


def _emergency_greeting_reply_text(
    *,
    lang: str,
    agent_mode: bool = False,
    message: str = "",
) -> str:
    """Salutation courte — repli local uniquement (Gemini indisponible)."""
    low = (message or "").lower().strip()
    if lang == "en":
        if re.match(r"^good\s+evening", low):
            salutation = "Good evening"
        elif re.match(r"^hi\b", low):
            salutation = "Hi"
        elif re.match(r"^(thanks|merci)", low):
            return "You're welcome! What would you like to check?"
        else:
            salutation = "Hello"
        mode = "Agent" if agent_mode else "Analysis"
        return f"{salutation} 👋 How can I help you? (Local mode — {mode})"
    if re.match(r"^(merci|thanks)", low):
        return "Avec plaisir ! Que puis-je faire d'autre pour vous ?"
    if re.match(r"^bonsoir", low):
        salutation = "Bonsoir"
        closing = "Que souhaitez-vous vérifier ce soir ?"
    elif re.match(r"^(salut|coucou)", low):
        salutation = "Salut"
        closing = "Comment puis-je vous aider ?"
    else:
        salutation = "Bonjour"
        closing = "Que puis-je vérifier pour vous sur la plateforme ?"
    return f"{salutation} 👋 {closing}"


def _degraded_user_footnote(reason: str | None) -> str:
    if reason == "quota":
        return (
            "\n\n_IA Gemini temporairement saturée — réponse locale. "
            "Réessayez dans quelques minutes._"
        )
    if reason == "overload":
        return "\n\n_API surchargée — réponse locale en attendant le rétablissement._"
    return ""


def _try_emergency_local_reply(
    message: str,
    *,
    agent_type: str,
    agent_mode: bool,
    lang: str,
    llm_failure: str | None = None,
) -> dict[str, Any] | None:
    """Salutations et métadonnées sans LLM — uniquement si Gemini est indisponible."""
    if _is_greeting_message(message):
        reply = _emergency_greeting_reply_text(
            lang=lang, agent_mode=agent_mode, message=message,
        )
        footnote = _degraded_user_footnote(llm_failure)
        if footnote:
            reply = f"{reply}{footnote}"
        response = _deterministic_tool_response(
            classification_intent=INTENT_ADMIN_QUERY,
            tool_name="greeting",
            reply=reply,
            message=message,
            agent_type=agent_type,
            humanize=False,
            llm_provider="local",
            llm_degraded=True,
        )
        return response

    return _try_local_intent_reply(
        message,
        agent_type=agent_type,
        agent_mode=agent_mode,
        llm_failure=llm_failure,
    )


def _try_greeting_reply(
    message: str,
    *,
    agent_type: str,
    agent_mode: bool,
    lang: str,
) -> dict[str, Any] | None:
    if not _is_greeting_message(message):
        return None
    return _deterministic_tool_response(
        classification_intent=INTENT_ADMIN_QUERY,
        tool_name="greeting",
        reply=_greeting_reply_text(lang=lang, agent_mode=agent_mode, message=message),
        message=message,
        agent_type=agent_type,
        humanize=False,
    )


def _copilot_security_block(admin: User, message: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.prompt_guard_enabled:
        return None
    risk = assess_user_message(message)
    if not must_block_preferences(risk):
        return None
    lang = _resolve_copilot_language(admin, message)
    return {
        "reply": prompt_injection_refusal(lang),
        "intent": INTENT_SECURITY,
        "agent_type": "security",
        "agent_type_label": "Jarvis",
        "mission_id": None,
        "action_executed": False,
        "needs_approval": False,
        "approval_id": None,
        "analysis_only": True,
        "agent_steps": [],
        "agent_reasoning": None,
        "conversation_id": None,
        "llm_provider": None,
        "gpt_slug": SLUG_ADMIN,
        "knowledge_hits": 0,
        "tools_used": [],
    }


def format_tools_catalog_reply(*, agent_mode: bool = False) -> str:
    """Catalogue des outils backend admin — sans appel LLM."""
    from app.services.gpt.tool_registry import TOOL_DEFINITIONS

    lines = [
        "Voici les **outils backend** dont je dispose pour interroger la plateforme Globex FedEx :",
        "",
    ]
    index = 0
    for tool in TOOL_DEFINITIONS:
        if SLUG_ADMIN not in tool.gpt_slugs:
            continue
        index += 1
        desc = (tool.description or "").split(".")[0].strip()
        if len(desc) > 140:
            desc = desc[:137] + "…"
        lines.append(f"{index}. **{tool.name}** — {desc}.")
    lines.extend(
        [
            "",
            "Je coordonne aussi **6 agents spécialisés** (tracking, users, tickets, logs, sécurité, synthèse). "
            "Demandez « liste des agents » pour le détail.",
        ]
    )
    return "\n".join(lines)


def _message_asks_tools_catalog(message: str) -> bool:
    text = (message or "").lower()
    if re.search(r"\b(outils?|tools?)\b", text):
        if re.search(
            r"\b(disposition|disponible|available|as[-\s]?tu|avez|have|backend|métier|metier)\b",
            text,
        ):
            return True
        if re.search(r"quels?\s+(?:sont\s+)?(?:les\s+)?(?:outils?|tools?)", text):
            return True
    return False


def _message_asks_security(message: str) -> bool:
    text = (message or "").lower()
    return bool(
        re.search(
            r"\b(s[eé]curit[eé]|security|ids|intrusion|incident[s]?)\b",
            text,
            re.I,
        )
    )


def _try_deterministic_security(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    lang: str = "fr",
) -> dict[str, Any] | None:
    """Incidents sécurité — outil direct sans LLM (réponse rapide)."""
    if not _message_asks_security(message):
        return None
    from app.services.ai_assistant.tool_executor import (
        build_tool_context,
        execute_enterprise_tool,
    )
    from app.services.gpt.tool_synthesis import synthesize_admin_tool_turn

    ctx = build_tool_context(db, admin, analysis_mode=True, ui_language=lang)
    item = execute_enterprise_tool(
        ctx, "get_security_alerts", {"status": "open", "limit": 20},
    )
    payloads = [item]
    fallback = synthesize_admin_tool_turn(
        task=message,
        tool_payloads=payloads,
        ui_language=lang,
    )
    payload = item.get("response") or {}
    if payload.get("message") and not fallback:
        fallback = str(payload["message"])
    return _deterministic_tool_response(
        classification_intent="admin_security",
        tool_name="get_security_alerts",
        reply=fallback or "Aucun incident sécurité ouvert trouvé.",
        message=message,
        agent_type=agent_type,
        humanize=False,
        llm_provider="local",
        llm_degraded=False,
        tool_payload=payload,
    )


def _try_pre_llm_admin_routes(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    agent_mode: bool,
    lang: str,
    context: str = "",
    hist_text: str | None = None,
    copilot_state: dict[str, Any] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Réponses locales et outils métier **avant** tout appel Gemini/Ollama."""
    greeting = _try_greeting_reply(
        message, agent_type=agent_type, agent_mode=agent_mode, lang=lang,
    )
    if greeting:
        greeting["llm_provider"] = "local"
        greeting["llm_degraded"] = False
        greeting["language"] = lang
        return greeting

    from app.services.ai_assistant.copilot_pipeline import try_copilot_pipeline

    pipeline_result = try_copilot_pipeline(
        db, admin, message,
        copilot_state=copilot_state,
        conversation_history=conversation_history,
        agent_type=agent_type,
    )
    if pipeline_result:
        from app.services.ai_assistant.response_builder import enrich_copilot_response
        pipeline_result["language"] = lang
        return enrich_copilot_response(pipeline_result)

    from app.services.ai_assistant.context_export_engine import try_context_export_turn

    context_export = try_context_export_turn(
        db,
        admin,
        message,
        copilot_state=copilot_state,
        conversation_history=conversation_history,
        agent_mode=agent_mode,
        agent_type=agent_type,
    )
    if context_export:
        return context_export

    from app.services.ai_assistant.specialized_routes import try_specialized_route

    specialized = try_specialized_route(
        db, admin, message, agent_mode=agent_mode, lang=lang,
        copilot_state=copilot_state,
    )
    if specialized:
        return specialized

    if _message_asks_tools_catalog(message):
        return _deterministic_tool_response(
            classification_intent=INTENT_CAPABILITIES,
            tool_name="tools_catalog",
            reply=format_tools_catalog_reply(agent_mode=agent_mode),
            message=message,
            agent_type=agent_type,
            humanize=False,
            llm_provider="local",
            llm_degraded=False,
        )

    cap = _try_deterministic_capabilities(
        message, agent_type=agent_type, agent_mode=agent_mode,
    )
    if cap:
        cap["llm_provider"] = "local"
        cap["llm_degraded"] = False
        return cap

    local = _try_local_intent_reply(
        message,
        agent_type=agent_type,
        agent_mode=agent_mode,
        llm_failure=None,
    )
    if local:
        local["llm_degraded"] = False
        local["llm_provider"] = "local"
        return local

    security = _try_deterministic_security(
        db, admin, message, agent_type=agent_type, lang=lang,
    )
    if security:
        return security

    data_route = _try_deterministic_copilot_routes(
        db,
        admin,
        message,
        agent_type=agent_type,
        context=context,
        hist_text=hist_text,
        agent_mode=agent_mode,
        humanize=True,
        force_degraded=True,
        copilot_state=copilot_state,
    )
    if data_route:
        data_route["llm_provider"] = "local"
        data_route["llm_degraded"] = False
        return data_route

    return None


def format_agent_catalog_reply(*, agent_mode: bool = False) -> str:
    """Réponse lisible sur les agents copilot — sans appel LLM (repli quota/timeout)."""
    lines = [
        "Le copilot Globex coordonne **6 agents spécialisés** :",
        "",
    ]
    for index, (key, label) in enumerate(AGENT_LABELS.items(), start=1):
        meta = AGENT_ROLE_META.get(key, {})
        tools = meta.get("tools") or []
        action = meta.get("action", "—")
        detail = ", ".join(tools) if tools else str(action)
        lines.append(f"{index}. **{label}** (`{key}`) — {detail}.")
    lines.append("")
    if agent_mode:
        lines.append(
            "Mode **Agent** : ces agents peuvent **exécuter** des actions "
            "(exports PDF/Excel, suspension de compte…) avec approbation si l'action est sensible."
        )
    else:
        lines.append(
            "Mode **Analyse** actuel : consultation et conseil sur les données. "
            "Passez en mode **Agent** pour déclencher des actions."
        )
    return "\n".join(lines)


def build_agent_catalog_context() -> str:
    """Catalogue des agents copilot — injecté dans le contexte Gemini (données serveur)."""
    lines = [
        "CATALOGUE AGENTS COPILOT GLOBEX (source serveur — données fiables) :",
        "",
    ]
    for key, label in AGENT_LABELS.items():
        meta = AGENT_ROLE_META.get(key, {})
        tools = meta.get("tools") or []
        action = meta.get("action", "—")
        lines.append(f"**{label}** (identifiant : `{key}`)")
        lines.append(f"  - Rôle principal : {action}")
        lines.append(f"  - Capacités : {', '.join(tools) if tools else '—'}")
        lines.append("")
    return "\n".join(lines)


def _message_asks_mode_comparison(message: str) -> bool:
    text = (message or "").lower()
    if not re.search(r"\b(mode|analyse|analysis|agent)\b", text, re.I):
        return False
    return bool(
        re.search(
            r"(diff[ée]rence|compare|versus|\bvs\.?\b|qu.?est.ce|what.?s the|between|entre)",
            text,
            re.I,
        )
    )


def _mode_comparison_reply_text(*, agent_mode: bool = False) -> str:
    analyse = (
        "**Mode Analyse** — consultation et conseil uniquement. "
        "Je lis les données plateforme (colis, users, tickets, logs) et je réponds, "
        "sans exécuter d'action (pas d'export PDF, pas de suspension de compte)."
    )
    agent = (
        "**Mode Agent** — exécution d'actions avec outils : export PDF/Excel, "
        "suspension de compte, etc. Les actions sensibles demandent votre approbation admin."
    )
    current = (
        "Vous êtes actuellement en **mode Agent**."
        if agent_mode
        else "Vous êtes actuellement en **mode Analyse**."
    )
    return (
        "Voici la différence entre les deux modes de Jarvis :\n\n"
        f"- {analyse}\n"
        f"- {agent}\n\n"
        f"{current} Basculez via le sélecteur en haut de l'assistant IA."
    )


def _try_local_intent_reply(
    message: str,
    *,
    agent_type: str,
    agent_mode: bool = False,
    llm_failure: str | None = None,
) -> dict[str, Any] | None:
    """Réponses métadonnées sans LLM — catalogue agents/outils, comparaison de modes."""
    intent = classify_intent(message, SLUG_ADMIN).intent
    degraded = bool(llm_failure)
    if intent == INTENT_ADMIN_AGENTS:
        reply = format_agent_catalog_reply(agent_mode=agent_mode)
        if llm_failure:
            reply = _append_degraded_notice(reply, reason=llm_failure)
        return _deterministic_tool_response(
            classification_intent=INTENT_ADMIN_AGENTS,
            tool_name="agent_catalog",
            reply=reply,
            message=message,
            agent_type=agent_type,
            humanize=False,
            llm_provider="local",
            llm_degraded=degraded,
        )
    if intent == INTENT_CAPABILITIES:
        if _message_asks_tools_catalog(message):
            reply = format_tools_catalog_reply(agent_mode=agent_mode)
            tool_name = "tools_catalog"
        else:
            reply = _capabilities_reply_text(agent_mode=agent_mode)
            tool_name = "capabilities"
        if llm_failure:
            reply = _append_degraded_notice(reply, reason=llm_failure)
        return _deterministic_tool_response(
            classification_intent=INTENT_CAPABILITIES,
            tool_name=tool_name,
            reply=reply,
            message=message,
            agent_type=agent_type,
            humanize=False,
            llm_provider="local",
            llm_degraded=degraded,
        )
    if _message_asks_mode_comparison(message):
        reply = _mode_comparison_reply_text(agent_mode=agent_mode)
        if llm_failure:
            reply = _append_degraded_notice(reply, reason=llm_failure)
        return _deterministic_tool_response(
            classification_intent=INTENT_CAPABILITIES,
            tool_name="mode_comparison",
            reply=reply,
            message=message,
            agent_type=agent_type,
            humanize=False,
            llm_provider="local",
            llm_degraded=bool(llm_failure),
        )
    return None


def _append_degraded_notice(reply: str, *, reason: str | None) -> str:
    if reason == "auth":
        return (
            f"{reply}\n\n"
            "_Clé API Gemini refusée (erreur 401). Vérifiez `GEMINI_API_KEY` dans `.env` "
            "(clé AI Studio : standard `AIza…` ou autorisation `AQ.…`) puis redémarrez le backend._"
        )
    if reason == "quota":
        return (
            f"{reply}\n\n"
            "_Moteur IA Gemini temporairement indisponible (quota dépassé). "
            "Réponse générée depuis le catalogue serveur — réessayez dans quelques minutes "
            "pour une synthèse IA personnalisée._"
        )
    if reason == "overload":
        return (
            f"{reply}\n\n"
            "_API Gemini surchargée — réponse locale en attendant le rétablissement._"
        )
    return reply


def _capabilities_reply_text(*, agent_mode: bool = False) -> str:
    if agent_mode:
        mode_line = (
            "Mode actuel : **Agent** — j'exécute les actions (export PDF, suspension compte…) "
            "avec approbation admin si l'action est sensible."
        )
    else:
        mode_line = (
            "Mode actuel : **Analyse** — je consulte les données et conseille. "
            "Activez le mode Agent pour exécuter des actions (export PDF, suspendre un compte…)."
        )
    return (
        "Je suis **Jarvis**, assistant Super Admin Globex FedEx. Voici ce que je peux faire pour vous :\n\n"
        "- **Suivi & expéditions** — statuts colis FedEx, retards, numéros de suivi\n"
        "- **Support client** — tickets ouverts, priorités, réponses\n"
        "- **Comptes utilisateurs** — liste, actifs, suspendus, administrateurs\n"
        "- **Conversations chat** — sessions clients/employés, titres, aperçus, statuts\n"
        "- **Journaux & exports** — logs d'activité, export PDF ou Excel (24h, 2h…)\n"
        "- **Sécurité & notifications** — incidents, alertes, tentatives d'intrusion\n"
        "- **Synthèses KPI** — état global de la plateforme\n\n"
        f"{mode_line}\n\n"
        "Exemples : « Liste les tickets ouverts », « Logs des dernières 24h », "
        "« Donne-moi tous les users », « Exporte les logs en PDF ou Excel »."
    )


def _message_asks_for_capabilities(message: str) -> bool:
    return classify_intent(message, SLUG_ADMIN).intent == INTENT_CAPABILITIES


def _try_deterministic_capabilities(
    message: str,
    *,
    agent_type: str,
    agent_mode: bool = False,
) -> dict[str, Any] | None:
    if classify_intent(message, SLUG_ADMIN).intent != INTENT_CAPABILITIES:
        return None
    return _deterministic_tool_response(
        classification_intent=INTENT_CAPABILITIES,
        tool_name="capabilities",
        reply=_capabilities_reply_text(agent_mode=agent_mode),
        message=message,
        agent_type=agent_type,
        humanize=False,
    )


def _parse_user_tool_args(message: str) -> dict[str, Any]:
    """Extrait filtres role/statut depuis une question admin en langage naturel."""
    text = (message or "").lower()
    args: dict[str, Any] = {"limit": 50}
    if re.search(r"\b(admins?|administrateurs?)\b", text) and "utilisateur" not in text and "user" not in text:
        args["role"] = "admin"
    elif re.search(r"\b(employ[eé]s?|employees?)\b", text):
        args["role"] = "employe"
    elif re.search(r"\bclients?\b", text):
        args["role"] = "client"
    if re.search(r"\b(suspendu[s]?|suspended)\b", text):
        args["status"] = "suspended"
    elif re.search(r"\b(actifs?|active)\b", text):
        args["status"] = "active"
    return args


def _is_users_list_follow_up(message: str, conversation_history: str | None) -> bool:
    from app.services.gpt.tool_synthesis import is_users_list_follow_up

    return is_users_list_follow_up(message, conversation_history)


def _resolve_ticket_status_filter(message: str) -> str:
    text = (message or "").lower()
    if re.search(r"\b(fermé|fermes|closed)\b", text):
        return "closed"
    if re.search(r"\b(résolu|resolu|resolved)\b", text):
        return "resolved"
    if re.search(r"\b(pending|en attente)\b", text):
        return "pending"
    return "open"


def _parse_notification_limit(message: str) -> int:
    text = (message or "").lower()
    m = re.search(r"\b(dernier|derniers|dernières|dernieres)\s+(\d{1,2})\b", text)
    if m:
        return min(max(int(m.group(2)), 1), 50)
    m = re.search(r"\b(\d{1,2})\s*(derniers?|dernières?|dernieres?|notifications?|notifs?)\b", text)
    if m:
        return min(max(int(m.group(1)), 1), 50)
    return 10


def _parse_notification_tool_args(message: str) -> dict[str, Any]:
    text = (message or "").lower()
    args: dict[str, Any] = {"limit": _parse_notification_limit(message)}
    if re.search(r"\b(non lues?|pas lues?|unread)\b", text):
        args["unread_only"] = True
    if re.search(r"\b(critiques?|critical|urgent)\b", text):
        args["critical_only"] = True
    return args


def _try_deterministic_admin_notifications(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    force_degraded: bool = False,
    copilot_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from app.services.gpt.copilot_conversation_state import (
        CopilotConversationState,
        is_export_only_message,
        merge_conversation_state,
    )

    state = merge_conversation_state(copilot_state, None)
    if is_export_only_message(message, state):
        return None

    classification = classify_intent(message, SLUG_ADMIN)
    if classification.intent != INTENT_ADMIN_NOTIFICATIONS and not _message_asks_for_notifications(message):
        return None

    handler = HANDLERS.get("analyze_notifications")
    if handler is None:
        return None

    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(tool_ctx, _parse_notification_tool_args(message))
    if not result.success:
        return None

    tool_payload = {"status": "ok", **result.data}
    intent = (
        classification.intent
        if classification.intent == INTENT_ADMIN_NOTIFICATIONS
        else INTENT_ADMIN_NOTIFICATIONS
    )
    return _deterministic_tool_response(
        classification_intent=intent,
        tool_name="analyze_notifications",
        message=message,
        agent_type=agent_type,
        ui_language=admin.preferred_language or "fr",
        tool_payload=tool_payload,
        force_degraded=force_degraded,
        copilot_state=copilot_state,
    )


def _try_deterministic_admin_conversations(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    force_degraded: bool = False,
) -> dict[str, Any] | None:
    classification = classify_intent(message, SLUG_ADMIN)
    if classification.intent != INTENT_ADMIN_CONVERSATIONS and not _message_asks_for_conversations(message):
        return None

    handler = HANDLERS.get("analyze_conversations")
    if handler is None:
        return None

    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(tool_ctx, {"limit": 40})
    if not result.success:
        return None

    intent = (
        classification.intent
        if classification.intent == INTENT_ADMIN_CONVERSATIONS
        else INTENT_ADMIN_CONVERSATIONS
    )
    return _deterministic_tool_response(
        classification_intent=intent,
        tool_name="analyze_conversations",
        message=message,
        agent_type=agent_type,
        ui_language=admin.preferred_language or "fr",
        tool_payload={"status": "ok", **result.data},
        force_degraded=force_degraded,
    )


def _deterministic_tool_response(
    *,
    classification_intent: str,
    tool_name: str,
    message: str,
    agent_type: str,
    ui_language: str = "fr",
    humanize: bool = True,
    llm_provider: str | None = None,
    llm_degraded: bool = False,
    tool_payload: dict[str, Any] | None = None,
    reply: str | None = None,
    conversation_history: str | None = None,
    hours: int | None = None,
    ticket_status: str | None = None,
    tracking_limit: int | None = None,
    force_degraded: bool = False,
    copilot_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Repli secours — payload JSON outil → réponse adaptée à l'intention + mémoire session."""
    from app.services.ai_assistant.memory_pipeline import (
        attach_memory_to_response,
        build_memory_from_state,
        classify_turn,
        format_response_for_intent,
        pipeline_should_use_direct_format,
        update_memory_after_tool,
    )

    memory = build_memory_from_state(copilot_state)
    intent_v2 = classify_turn(message, memory=memory)
    payload = tool_payload if tool_payload is not None else {"status": "ok"}
    data = {k: v for k, v in payload.items() if k != "status"}

    if humanize and tool_name not in {"capabilities", "greeting", "agent_catalog"}:
        from app.services.gpt.tool_synthesis import (
            degraded_format_tool_payload,
            synthesize_copilot_reply,
        )

        direct = format_response_for_intent(
            intent_v2, tool_name, data, ui_language=ui_language, message=message,
        )
        fallback = degraded_format_tool_payload(
            tool_name,
            payload,
            message=message,
            conversation_history=conversation_history,
            ui_language=ui_language,
            hours=hours,
            ticket_status=ticket_status,
            tracking_limit=tracking_limit,
        )
        if pipeline_should_use_direct_format(intent_v2) or force_degraded:
            final_reply = direct or fallback or "Les données n'ont pas pu être récupérées."
            llm_provider = "local" if pipeline_should_use_direct_format(intent_v2) else "degraded"
            llm_degraded = llm_provider == "degraded"
        elif force_degraded:
            final_reply = fallback or direct or "Les données n'ont pas pu être récupérées."
            llm_provider = "degraded"
            llm_degraded = True
        else:
            final_reply, provider = synthesize_copilot_reply(
                task=message,
                tool_payloads=[{"name": tool_name, "response": payload}],
                ui_language=ui_language,
                fallback=direct or fallback or "Les données n'ont pas pu être récupérées.",
            )
            llm_degraded = provider == "degraded"
            llm_provider = provider
    else:
        final_reply = reply or ""
        llm_provider = llm_provider or "deterministic"

    memory = update_memory_after_tool(
        memory,
        tool_name=tool_name,
        payload=data,
        intent=intent_v2,
        reply=final_reply,
    )

    response: dict[str, Any] = {
        "reply": final_reply,
        "intent": classification_intent,
        "agent_type": agent_type,
        "agent_type_label": "Jarvis",
        "mission_id": None,
        "action_executed": False,
        "needs_approval": False,
        "approval_id": None,
        "analysis_only": True,
        "agent_steps": [{"label": tool_name, "status": "done", "detail": None}],
        "agent_reasoning": {
            "objective": message[:200],
            "plan": [f"Outil : {tool_name}"],
            "action_tool": tool_name,
            "action_label": tool_name,
        },
        "conversation_id": None,
        "llm_degraded": llm_degraded,
        "llm_provider": llm_provider,
        "gpt_slug": SLUG_ADMIN,
        "knowledge_hits": 0,
        "tools_used": [tool_name],
        "query_type": intent_v2.action,
        "specific_intent": intent_v2.specific_intent,
    }
    return attach_memory_to_response(
        response,
        memory=memory,
        copilot_state=copilot_state,
        tools_used=[tool_name],
        tool_payloads=[{"name": tool_name, "response": payload}],
    )


def _attach_copilot_state(
    response: dict[str, Any],
    state: Any,
    *,
    tools_used: list[str] | None = None,
    tool_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.gpt.copilot_conversation_state import update_state_after_tools

    if tools_used:
        state = update_state_after_tools(
            state,
            tools_used=tools_used,
            tool_payloads=tool_payloads or [],
        )
    response["copilot_state"] = state.to_dict()
    return response


def _try_conversation_context_turn(
    db: Session,
    admin: User,
    message: str,
    *,
    conversation_history: list[dict[str, str]] | None,
    copilot_state: dict[str, Any] | None,
    agent_mode: bool,
    agent_type: str,
    ui_lang: str,
) -> dict[str, Any] | None:
    """Exports contextuels uniquement — jamais pour une demande de liste."""
    from app.services.gpt.copilot_conversation_state import (
        merge_conversation_state,
        resolve_copilot_turn,
    )
    from app.services.gpt.copilot_context_resolver import (
        clarify_export_reply,
        execute_contextual_export,
    )

    state = merge_conversation_state(copilot_state, conversation_history)
    resolved = resolve_copilot_turn(message, state, messages=conversation_history)

    if resolved.kind == "security_block":
        return {
            "reply": prompt_injection_refusal(ui_lang),
            "intent": INTENT_SECURITY,
            "agent_type": "security",
            "agent_type_label": "Jarvis",
            "mission_id": None,
            "action_executed": False,
            "needs_approval": False,
            "approval_id": None,
            "analysis_only": True,
            "agent_steps": [],
            "agent_reasoning": None,
            "conversation_id": None,
            "llm_provider": None,
            "gpt_slug": SLUG_ADMIN,
            "knowledge_hits": 0,
            "tools_used": [],
            "copilot_state": state.to_dict(),
        }

    if resolved.kind == "clarify_export":
        clarify_text, clarify_provider = clarify_export_reply(ui_lang, message)
        return {
            "reply": clarify_text,
            "intent": "admin_export",
            "agent_type": agent_type,
            "agent_type_label": "Jarvis",
            "mission_id": None,
            "action_executed": False,
            "needs_approval": False,
            "approval_id": None,
            "analysis_only": True,
            "agent_steps": [],
            "agent_reasoning": None,
            "conversation_id": None,
            "llm_provider": clarify_provider,
            "llm_degraded": clarify_provider == "degraded",
            "gpt_slug": SLUG_ADMIN,
            "knowledge_hits": 0,
            "tools_used": [],
            "copilot_state": state.to_dict(),
        }

    if resolved.kind == "contextual_export":
        result = execute_contextual_export(
            db, admin, resolved, state, agent_mode=agent_mode, user_message=message,
        )
        if result:
            result.setdefault("agent_type", agent_type)
            result.setdefault("agent_type_label", "Jarvis")
            return result

    return None


def _merge_state_instruction(context: str, copilot_state: dict[str, Any] | None, history: list | None) -> str:
    from app.services.gpt.copilot_conversation_state import (
        build_state_server_instruction,
        merge_conversation_state,
    )

    state = merge_conversation_state(copilot_state, history)
    instr = build_state_server_instruction(state)
    if not instr:
        return context
    return f"{context}\n\n{instr}".strip()


def _message_asks_for_users(message: str) -> bool:
    """Détecte une demande explicite de comptes utilisateurs (pas les logs ni conversations)."""
    text = (message or "").lower()
    if re.search(r"\b(conversations?|discussions?|chats?|échanges?|echanges?)\b", text):
        return False
    if classify_intent(message, SLUG_ADMIN).intent == INTENT_ADMIN_USERS:
        return True
    return bool(re.search(r"\b(users?|utilisateurs?|comptes?)\b", text))


def _message_asks_for_notifications(message: str) -> bool:
    return bool(re.search(r"\b(notifications?|notifs?|alertes?)\b", (message or "").lower()))


def _message_asks_for_tickets(message: str) -> bool:
    return bool(re.search(r"\b(tickets?|support|plaintes?)\b", (message or "").lower()))


def _message_asks_for_logs(message: str) -> bool:
    text = (message or "").lower()
    if _message_asks_for_users(message) or _message_asks_for_notifications(message):
        return False
    return bool(
        re.search(
            r"\b(logs?|journaux|activit[eé]|événements?|evenements?|historique)\b",
            text,
        )
    )


def _message_asks_for_conversations(message: str) -> bool:
    return bool(re.search(r"\b(conversations?|discussions?|chats?|sessions?)\b", (message or "").lower()))


def _message_asks_for_tracking(message: str) -> bool:
    return bool(
        re.search(r"\b(tracking|colis|exp[eé]ditions?|shipments?|suivi|livraisons?)\b", (message or "").lower())
    )


def _wants_logs_pdf(message: str, conversation_history: str | None = None) -> bool:
    return _wants_logs_export(message, conversation_history, fmt="pdf")


def _wants_logs_export(
    message: str,
    conversation_history: str | None = None,
    *,
    fmt: str | None = None,
) -> bool:
    if _message_asks_for_users(message):
        return False
    text = (message or "").lower()
    resolved = _resolve_logs_export_format(message, conversation_history)
    if fmt and resolved != fmt:
        return False
    if resolved:
        if re.search(r"\b(logs?|journaux|activit)\b", text):
            return True
        if conversation_history and _is_logs_export_follow_up(message, conversation_history):
            return True
        return False
    elif conversation_history and _is_logs_export_follow_up(message, conversation_history):
        return True
    return False


def _resolve_logs_export_format(
    message: str,
    conversation_history: str | None = None,
) -> str | None:
    """Retourne 'pdf' ou 'xlsx' si une exportation de logs est demandée."""
    msg_l = (message or "").lower()
    hist = (conversation_history or "").lower()
    wants_excel = bool(re.search(r"\b(excel|xlsx|xls|tableur|csv)\b", msg_l))
    wants_pdf = bool(re.search(r"\b(pdf)\b", msg_l))
    if wants_excel and not wants_pdf:
        return "xlsx"
    if wants_pdf and not wants_excel:
        return "pdf"
    if wants_excel:
        return "xlsx"
    if wants_pdf:
        return "pdf"
    # Pour les relances très courtes, on réutilise le format mentionné juste avant.
    if _is_affirmation_follow_up(message, conversation_history):
        if re.search(r"\b(excel|xlsx|csv|tableur)\b", hist):
            return "xlsx"
        if re.search(r"\bpdf\b", hist):
            return "pdf"
    return None


def _is_affirmation_follow_up(message: str, conversation_history: str | None) -> bool:
    if _message_asks_for_capabilities(message):
        return False
    msg_l = (message or "").lower().strip()
    hist = (conversation_history or "").lower()
    if not hist or len(msg_l) > 80:
        return False
    if not re.search(r"\b(excel|xlsx|csv|pdf|export|fichier|format|logs?|journaux)\b", hist):
        return False
    return bool(
        re.search(
            r"\b(?:"
            r"oui|ok|d'accord|vas[- ]?y|fais[- ]?le|fait[- ]?le|"
            r"maintenant|mtn|lance|go|"
            r"tu peux la faire|tu peux le faire|tu peux maintenant|"
            r"peux[- ]?tu le faire|peux[- ]?tu la faire|"
            r"pouvez[- ]?vous le faire|pouvez[- ]?vous la faire"
            r")\b",
            msg_l,
        )
    )


def _is_logs_pdf_follow_up(message: str, conversation_history: str | None) -> bool:
    return _is_logs_export_follow_up(message, conversation_history) and (
        _resolve_logs_export_format(message, conversation_history) == "pdf"
        or bool(re.search(r"\b(pdf|format|export|télécharger|telecharger|forme)\b", (message or "").lower()))
    )


def _is_logs_export_follow_up(message: str, conversation_history: str | None) -> bool:
    if _message_asks_for_capabilities(message):
        return False
    msg_l = (message or "").lower().strip()
    hist = (conversation_history or "").lower()
    if not hist or len(msg_l) > 120:
        return False
    if _message_asks_for_users(message):
        return False
    logs_ctx = bool(
        re.search(
            r"\b(logs?|journaux|analyze_logs|activit|entrées?|entrees?|"
            r"journal d'activité|journaux d'activité|copilot_query)\b",
            hist,
        )
    )
    if not logs_ctx:
        return False
    if re.search(
        r"\b(pdf|excel|xlsx|xls|csv|format|export|télécharger|telecharger|forme|tableur|fichier)\b",
        msg_l,
    ):
        return True
    if _is_affirmation_follow_up(message, conversation_history):
        return True
    if re.search(r"\b(les|ceux|ça|ca|donne|sous forme|souhaite|veux)\b", msg_l):
        return bool(_resolve_logs_export_format(message, conversation_history))
    return False


_TRACKING_STATUS_FOLLOW_UP = re.compile(
    r"\b(pdf|état|etat|avancement|statut|progress|chacun|entre eux|mets? les)\b",
    re.I,
)


def _try_tracking_status_follow_up(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    conversation_history: str | None,
    llm_failure: str | None = None,
) -> dict[str, Any] | None:
    """Relance : statut FedEx des numéros déjà cités dans l'historique (sans LLM)."""
    if not conversation_history or not _TRACKING_STATUS_FOLLOW_UP.search(message or ""):
        return None
    numbers = extract_tracking_numbers(conversation_history)
    if not numbers:
        numbers = extract_tracking_numbers(message or "")
    if not numbers:
        return None

    handler = HANDLERS.get("fedex_track_package")
    if handler is None:
        return None

    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    lines: list[str] = ["**État d'avancement des colis** (données FedEx temps réel) :", ""]
    ok_count = 0
    ok_numbers: list[str] = []
    for tn in numbers[:10]:
        result = handler(tool_ctx, {"tracking_number": tn})
        if result.success:
            ok_count += 1
            ok_numbers.append(tn)
            loc = result.data.get("current_location") or ""
            extra = f" — {loc}" if loc else ""
            lines.append(f"- **{tn}** : {result.data.get('status') or '—'}{extra}")
        else:
            lines.append(f"- **{tn}** : {result.error or 'introuvable'}")

    wants_pdf = bool(re.search(r"\bpdf\b", (message or "").lower()))
    export_spec: dict[str, Any] | None = None
    if wants_pdf and ok_numbers:
        export_spec = build_tracking_status_export_download(ok_numbers)
        lines.append("")
        lines.append(
            f"Export PDF prêt — {len(ok_numbers)} colis.\n"
            f"Téléchargez : **{export_spec['filename']}**."
        )

    reply = "\n".join(lines)
    if llm_failure == "auth" and not export_spec:
        reply = _append_degraded_notice(reply, reason="auth")

    response = _deterministic_tool_response(
        classification_intent=INTENT_ADMIN_TRACKING,
        tool_name="fedex_track_package",
        reply=reply,
        message=message,
        agent_type=agent_type,
        humanize=False,
        llm_provider="local",
        llm_degraded=bool(llm_failure) and not export_spec,
    )
    response["tools_used"] = ["fedex_track_package"] if ok_count else []
    if export_spec:
        response["export_download"] = export_spec
        response["action_executed"] = True
        response["analysis_only"] = False
    return response


def _try_logs_pdf_follow_up_export(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    conversation_history: str | None,
) -> dict[str, Any] | None:
    """Relance export (PDF/Excel) après des logs — export direct fiable."""
    if not _is_logs_export_follow_up(message, conversation_history):
        return None
    return _try_deterministic_admin_logs(
        db, admin, message, agent_type=agent_type, conversation_history=conversation_history,
    )


def _parse_logs_hours(message: str, conversation_history: str | None = None) -> int:
    combined = f"{conversation_history or ''}\n{message or ''}"
    return parse_log_period_hours(combined, default=24)


def _try_deterministic_admin_logs(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    conversation_history: str | None = None,
    force_degraded: bool = False,
) -> dict[str, Any] | None:
    if _message_asks_for_users(message):
        return None
    if re.search(r"\b(notifications?|notifs?)\b", (message or "").lower()):
        return None

    classification = classify_intent(message, SLUG_ADMIN)
    follow_up_export = _is_logs_export_follow_up(message, conversation_history)
    export_fmt = _resolve_logs_export_format(message, conversation_history)
    wants_export = bool(export_fmt) and (
        _wants_logs_export(message, conversation_history)
        or follow_up_export
    )
    ui_lang = admin.preferred_language or "fr"

    if wants_export and export_fmt:
        tool_name = (
            "export_activity_logs_excel" if export_fmt == "xlsx" else "export_activity_logs_pdf"
        )
        handler = HANDLERS.get(tool_name)
        if handler is None:
            return None
        hours = _parse_logs_hours(message, conversation_history)
        tool_ctx = ToolExecutionContext(
            db=db,
            user_id=admin.id,
            user_role="admin",
            gpt_slug=SLUG_ADMIN,
            actor_admin_id=admin.id,
            ui_language=admin.preferred_language or "fr",
        )
        result = handler(tool_ctx, {"hours": hours})
        if not result.success:
            return None
        export_spec = result.data.get("export_download") or {}
        filename = export_spec.get("filename") or f"activity-logs-{hours}h"
        tool_payload = {
            "status": "ok",
            "export_format": export_fmt,
            "entries": result.data.get("entries", 0),
            "hours": hours,
            "filename": filename,
            "export_download": export_spec,
        }
        response = _deterministic_tool_response(
            classification_intent=INTENT_ADMIN_LOGS,
            tool_name=tool_name,
            message=message,
            agent_type=agent_type,
            ui_language=ui_lang,
            tool_payload=tool_payload,
            force_degraded=force_degraded,
        )
        response["export_download"] = export_spec
        response["action_executed"] = True
        response["analysis_only"] = False
        return response

    if (
        classification.intent != INTENT_ADMIN_LOGS
        and not follow_up_export
        and not _message_asks_for_logs(message)
    ):
        return None

    handler = HANDLERS.get("analyze_logs")
    if handler is None:
        return None

    hours = _parse_logs_hours(message, conversation_history)
    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(tool_ctx, {"hours": hours, "limit": 50})
    if not result.success:
        return None

    return _deterministic_tool_response(
        classification_intent=INTENT_ADMIN_LOGS,
        tool_name="analyze_logs",
        message=message,
        agent_type=agent_type,
        ui_language=ui_lang,
        tool_payload={"status": "ok", "hours": hours, **result.data},
        hours=hours,
        force_degraded=force_degraded,
    )


def _parse_tracking_limit(message: str) -> int:
    text = (message or "").lower()
    for pattern in (
        r"\b(\d+)\s*(?:derni[eè]res?|last|recentes?|r[eé]centes?)\b",
        r"\b(?:derni[eè]res?|last)\s*(\d+)\b",
    ):
        m = re.search(pattern, text)
        if m:
            return min(max(int(m.group(1)), 1), 50)
    return 10


def _wants_tracking_users(message: str) -> bool:
    return bool(
        re.search(
            r"\b(par\s+quel|par\s+quelle|utilisateur|utilisateurs?|users?|comptes?)\b",
            (message or "").lower(),
        )
    )

def _is_simple_tracking_list_query(message: str) -> bool:
    """Liste / derniers trackings — pas les synthèses multi-domaines."""
    text = (message or "").lower()
    is_tracking = (
        classify_intent(message, SLUG_ADMIN).intent == INTENT_ADMIN_TRACKING
        or _message_asks_for_tracking(message)
    )
    if not is_tracking or _message_asks_for_users(message):
        return False
    if re.search(
        r"\b(logs?|journaux|tickets?|notifications?|priorit|incidents?|probl[eè]mes?|critiques?)\b",
        text,
    ):
        return False
    return True


def _try_deterministic_admin_tracking(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    humanize: bool = True,
    force_degraded: bool = False,
) -> dict[str, Any] | None:
    classification = classify_intent(message, SLUG_ADMIN)
    if (
        classification.intent != INTENT_ADMIN_TRACKING
        and not _message_asks_for_tracking(message)
    ) or _message_asks_for_users(message):
        return None

    handler = HANDLERS.get("analyze_tracking")
    if handler is None:
        return None

    limit = _parse_tracking_limit(message)
    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(tool_ctx, {"limit": limit})
    if not result.success:
        return None

    if humanize:
        return _deterministic_tool_response(
            classification_intent=INTENT_ADMIN_TRACKING,
            tool_name="analyze_tracking",
            message=message,
            agent_type=agent_type,
            ui_language=admin.preferred_language or "fr",
            tool_payload={"status": "ok", **result.data},
            tracking_limit=limit,
            force_degraded=force_degraded,
        )

    from app.services.gpt.tool_synthesis import degraded_format_tool_payload

    reply = degraded_format_tool_payload(
        "analyze_tracking",
        {"status": "ok", **result.data},
        message=message,
        ui_language=admin.preferred_language or "fr",
        tracking_limit=limit,
    )
    return _deterministic_tool_response(
        classification_intent=INTENT_ADMIN_TRACKING,
        tool_name="analyze_tracking",
        reply=reply,
        message=message,
        agent_type=agent_type,
        humanize=False,
        llm_provider="local",
        llm_degraded=True,
    )


def _try_deterministic_admin_tickets(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    force_degraded: bool = False,
) -> dict[str, Any] | None:
    classification = classify_intent(message, SLUG_ADMIN)
    if classification.intent != INTENT_ADMIN_TICKETS and not _message_asks_for_tickets(message):
        return None

    handler = HANDLERS.get("analyze_tickets")
    if handler is None:
        return None

    status = _resolve_ticket_status_filter(message)
    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(tool_ctx, {"status": status, "limit": 30})
    if not result.success:
        return None

    intent = (
        classification.intent
        if classification.intent == INTENT_ADMIN_TICKETS
        else INTENT_ADMIN_TICKETS
    )
    return _deterministic_tool_response(
        classification_intent=intent,
        tool_name="analyze_tickets",
        message=message,
        agent_type=agent_type,
        ui_language=admin.preferred_language or "fr",
        tool_payload={"status": "ok", "filter_status": status, **result.data},
        ticket_status=status,
        force_degraded=force_degraded,
    )


def _try_deterministic_admin_users(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    context: str,
    conversation_history: str | None = None,
    force_degraded: bool = False,
    copilot_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from app.services.gpt.copilot_conversation_state import (
        is_export_only_message,
        merge_conversation_state,
    )

    state = merge_conversation_state(copilot_state, None)
    if is_export_only_message(message, state):
        return None

    classification = classify_intent(message, SLUG_ADMIN)
    follow_up = _is_users_list_follow_up(message, conversation_history)
    if (
        classification.intent != INTENT_ADMIN_USERS
        and not follow_up
        and not _message_asks_for_users(message)
    ):
        return None

    handler = HANDLERS.get("analyze_users")
    if handler is None:
        return None

    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(tool_ctx, _parse_user_tool_args(message))
    if not result.success:
        return None

    intent = classification.intent if classification.intent == INTENT_ADMIN_USERS else INTENT_ADMIN_USERS
    return _deterministic_tool_response(
        classification_intent=intent,
        tool_name="analyze_users",
        message=message,
        agent_type=agent_type,
        ui_language=admin.preferred_language or "fr",
        tool_payload={"status": "ok", **result.data},
        conversation_history=conversation_history,
        force_degraded=force_degraded,
        copilot_state=copilot_state,
    )


def _build_operational_context(db: Session) -> str:
    stats = build_command_center(db)
    return (
        f"Contexte Globex Super Admin: "
        f"utilisateurs actifs={stats.hero_stats[2].value}, "
        f"expéditions aujourd'hui={stats.hero_stats[0].value}, "
        f"incidents ouverts={stats.open_incidents}, "
        f"requêtes FedEx aujourd'hui={stats.fedex_metrics.requests_today}."
    )


_DATA_QUERY_INTENTS = frozenset({
    INTENT_ADMIN_USERS,
    INTENT_ADMIN_TICKETS,
    INTENT_ADMIN_LOGS,
    INTENT_ADMIN_NOTIFICATIONS,
    INTENT_ADMIN_CONVERSATIONS,
    INTENT_ADMIN_TRACKING,
})

_ADMIN_PLATFORM_KEYWORDS = re.compile(
    r"\b("
    r"users?|utilisateurs?|comptes?|admins?|tickets?|logs?|journaux|notif|notifications?|"
    r"conversations?|discussions?|chats?|sessions?|documents?|rapports?|"
    r"suspendu|kpi|incident|s[eé]curit|menace|alerte|colis|exp[eé]ditions?|retards?|"
    r"liste les|donne[- ]moi|donne moi|affiche|montre les|combien"
    r")\b",
    re.I,
)

_ADMIN_SYNTHESIS_KEYWORDS = re.compile(
    r"\b("
    r"probl[eè]mes?|priorit[eé]s?|critiques?|synth[eè]se|op[eé]rationnel"
    r")\b.{0,50}\b(aujourd|jour|plateforme|admin|3|trois|cinq|5)\b|"
    r"\b(analyse|logs?|incidents?|retards?).{0,40}(priorit|critique|synth[eè]se)",
    re.I,
)

_FEDEX_GENERAL_QUESTION = re.compile(
    r"\b("
    r"combien de temps|d[eé]lai|delai|transit|livraison|frais|tarif|douane|"
    r"usa|u\.s\.a|etats[- ]unis|états[- ]unis|maroc|morocco|international|"
    r"fedex|express|standard|economy|priorit|zone|pays|country|"
    r"exp[eé]die|envoyer un colis|envoi vers"
    r")\b",
    re.I,
)


def _is_export_format_request(text: str) -> bool:
    """Demande de format/export — pas une pièce jointe à uploader."""
    return bool(
        re.search(r"\b(pdf|excel|xlsx|export)\b", text)
        and re.search(r"\b(format|forme|export|donne|les|sous|télécharger|telecharger)\b", text)
    )


def _is_fedex_general_question(text: str) -> bool:
    """Question logistique / délais / tarifs — RAG + Gemini, pas outils admin plateforme."""
    return bool(_FEDEX_GENERAL_QUESTION.search(text))


def _requires_platform_data_tools(
    message: str,
    intent: str | None = None,
    *,
    knowledge_hits: int = 0,
) -> bool:
    """True si la question exige des données plateforme via outils (pas RAG / FedEx général)."""
    resolved = intent or classify_intent(message, SLUG_ADMIN).intent
    if resolved in {INTENT_CAPABILITIES, INTENT_ADMIN_AGENTS, INTENT_KNOWLEDGE, INTENT_SECURITY}:
        return False
    text = (message or "").lower().strip()
    if re.match(r"^(bonjour|salut|hello|hi|merci|thanks|coucou)[\s!.?]*$", text):
        return False
    if _is_export_format_request(text):
        return False
    if _is_fedex_general_question(text):
        return False
    if _ADMIN_SYNTHESIS_KEYWORDS.search(text):
        return True
    if knowledge_hits > 0 and not _ADMIN_PLATFORM_KEYWORDS.search(text):
        return False
    if resolved in _DATA_QUERY_INTENTS:
        return True
    if resolved == INTENT_ADMIN_QUERY:
        return bool(_ADMIN_PLATFORM_KEYWORDS.search(text))
    return bool(_ADMIN_PLATFORM_KEYWORDS.search(text))


def _no_tools_data_reply(task: str | None = None) -> str:
    return (
        "Je n'ai pas pu récupérer les données nécessaires pour répondre de façon fiable."
    )


def _llm_failure_reason(exc: BaseException | None) -> str | None:
    text = str(exc or "").lower()
    if "401" in text or "403" in text or "invalid authentication" in text or "unauth" in text:
        return "auth"
    if "429" in text or "quota" in text or "exceeded" in text:
        return "quota"
    if "503" in text or "high demand" in text or "unavailable" in text:
        return "overload"
    return None


def _log_gemini_agent_failure(exc: BaseException, *, context_label: str = "analyse") -> str | None:
    reason = _llm_failure_reason(exc)
    if reason in ("quota", "overload"):
        logger.warning(
            "Gemini agent %s indisponible (%s) — repli Ollama/local.",
            context_label,
            reason,
        )
    else:
        logger.exception("Gemini agent %s échoué", context_label)
    return reason


def _gemini_agent_available(settings: Any) -> bool:
    return (
        bool(settings.gpt_tools_enabled)
        and bool(settings.llm_enabled)
        and gemini_api_key_usable()
        and not is_global_gemini_quota_exhausted()
    )


def _engine_unavailable_reply(*, reason: str | None = None) -> str:
    if _admin_copilot_uses_jarvis():
        if reason == "auth":
            return (
                "Jarvis (Ollama) est indisponible. Vérifiez qu'Ollama tourne "
                f"({get_settings().ollama_base_url}) et que le modèle "
                f"`{get_settings().ollama_model}` est installé (`ollama pull {get_settings().ollama_model}`)."
            )
        return (
            "Je n'ai pas pu joindre Jarvis (Ollama). "
            "Vérifiez qu'Ollama est démarré et que le modèle local est chargé, puis réessayez."
        )
    if reason == "auth":
        return (
            "Clé API Gemini refusée (erreur 401). "
            "Vérifiez `GEMINI_API_KEY` dans le fichier `.env` "
            "(clé AI Studio : standard `AIza…` ou autorisation `AQ.…` depuis "
            "https://aistudio.google.com/apikey), puis redémarrez le backend."
        )
    if reason == "quota":
        return (
            "Le quota API Gemini est momentanément dépassé (erreur 429). "
            "Réessayez dans quelques minutes, ou configurez Ollama en secours "
            "(LLM_PRIMARY_PROVIDER=ollama dans .env) si vous avez un modèle local."
        )
    if reason == "overload":
        return (
            "L'API Gemini est surchargée (erreur 503). Réessayez dans un instant — "
            "les routes automatiques (logs, users, exports) restent disponibles."
        )
    return (
        "Je n'ai pas pu joindre le moteur IA (Gemini indisponible et aucun secours actif). "
        "Réessayez dans quelques instants."
    )


def _is_false_injection_refusal(reply: str) -> bool:
    text = (reply or "").lower()
    return "prompt injection" in text or "cannot follow this instruction" in text


def _recover_false_injection_reply(
    db: Session,
    admin: User,
    task: str,
    *,
    agent_type: str,
    turn: Any,
    conversation_history: list[dict[str, str]] | None = None,
    copilot_state: dict[str, Any] | None = None,
    agent_mode: bool = False,
    ui_lang: str = "fr",
) -> dict[str, Any] | None:
    """Repli si Gemini refuse à tort une question métier admin."""
    if not _is_false_injection_refusal(getattr(turn, "reply", "") or ""):
        return None
    contextual = _try_conversation_context_turn(
        db, admin, task,
        conversation_history=conversation_history,
        copilot_state=copilot_state,
        agent_mode=agent_mode,
        agent_type=agent_type,
        ui_lang=ui_lang,
    )
    if contextual:
        return contextual
    from app.services.ai_assistant.specialized_routes import try_specialized_route

    specialized = try_specialized_route(
        db, admin, task, agent_mode=agent_mode, lang=ui_lang,
    )
    if specialized:
        return specialized
    return None


def _finalize_agent_reply(
    task: str,
    turn: Any,
    *,
    db: Session | None = None,
    admin: User | None = None,
    agent_type: str = "summary",
    context: str = "",
    hist_text: str | None = None,
    copilot_state: dict[str, Any] | None = None,
) -> str:
    """Bloque les réponses sans outils — repli pipeline déterministe avant message d'erreur."""
    kb_hits = len(getattr(turn, "knowledge_sources", None) or [])
    if (
        _requires_platform_data_tools(task, turn.intent, knowledge_hits=kb_hits)
        and not turn.tools_used
    ):
        if db is not None and admin is not None:
            try:
                from app.services.ai_assistant.copilot_pipeline import try_copilot_pipeline
                det = try_copilot_pipeline(
                    db, admin, task,
                    copilot_state=copilot_state,
                    agent_type=agent_type,
                )
                if det and (det.get("answer") or det.get("reply")):
                    return det.get("answer") or det.get("reply") or ""
            except Exception:
                logger.exception("[Copilot] pipeline fallback failed in _finalize_agent_reply")
        return _no_tools_data_reply(task)
    return turn.reply


def _build_agent_turn_response(
    turn: Any,
    *,
    task: str,
    agent_type: str,
    reply: str | None = None,
    copilot_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_reply = reply if reply is not None else turn.reply
    return {
        "reply": final_reply,
        "intent": turn.intent or agent_type,
        "agent_type": agent_type,
        "agent_type_label": "Jarvis",
        "mission_id": None,
        "action_executed": turn.action_executed,
        "needs_approval": turn.needs_approval,
        "approval_id": None,
        "analysis_only": not turn.action_executed,
        "agent_steps": turn.agent_steps,
        "agent_reasoning": {
            "objective": task[:200],
            "plan": [f"Outil : {t}" for t in turn.tools_used],
            "action_tool": turn.tools_used[-1] if turn.tools_used else "",
            "action_label": turn.tools_used[-1] if turn.tools_used else "Analyse",
        } if turn.tools_used else None,
        "conversation_id": None,
        "export_download": turn.export_download,
        "llm_degraded": (turn.llm_provider or "").lower() not in {"", "gemini", "jarvis", "ollama"},
        "llm_provider": turn.llm_provider,
        "gpt_slug": turn.gpt_slug,
        "knowledge_hits": len(turn.knowledge_sources),
        "tools_used": turn.tools_used,
        "copilot_state": copilot_state,
    }


def _build_analysis_unavailable_response(
    *,
    agent_type: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "reply": _engine_unavailable_reply(reason=reason),
        "intent": agent_type,
        "agent_type": agent_type,
        "agent_type_label": "Jarvis",
        "mission_id": None,
        "action_executed": False,
        "needs_approval": False,
        "approval_id": None,
        "analysis_only": True,
        "agent_steps": [],
        "agent_reasoning": None,
        "conversation_id": None,
        "llm_degraded": True,
        "llm_provider": None,
        "gpt_slug": SLUG_ADMIN,
        "knowledge_hits": 0,
        "tools_used": [],
    }


def _build_llm_fallback_response(
    *,
    reply: str,
    agent_type: str,
    intent: str | None,
    llm_provider: str | None,
    knowledge_hits: int,
) -> dict[str, Any]:
    degraded = (llm_provider or "").lower() not in {"", "gemini"}
    return {
        "reply": reply,
        "intent": intent or agent_type,
        "agent_type": agent_type,
        "agent_type_label": "Jarvis",
        "mission_id": None,
        "action_executed": False,
        "needs_approval": False,
        "approval_id": None,
        "analysis_only": True,
        "agent_steps": [],
        "agent_reasoning": None,
        "conversation_id": None,
        "export_download": None,
        "llm_degraded": degraded,
        "llm_provider": llm_provider,
        "gpt_slug": SLUG_ADMIN,
        "knowledge_hits": knowledge_hits,
        "tools_used": [],
    }


def _try_ollama_copilot_fallback(
    db: Session,
    admin: User,
    task: str,
    *,
    context: str,
    hist_text: str,
    agent_type: str,
    ui_language: str = "fr",
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    attached_document_name: str | None = None,
    llm_failure: str | None = None,
) -> dict[str, Any] | None:
    """Secours Ollama (model_gateway) quand la boucle Gemini agent échoue (429/503)."""
    if llm_failure not in ("quota", "overload"):
        return None
    if not get_settings().llm_enabled:
        return None
    try:
        reply, intent, provider, kb_hits = _admin_copilot_llm_fallback(
            db,
            admin,
            task,
            context=context,
            hist_text=hist_text,
            agent_type=agent_type,
            ui_language=ui_language,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
            fast_ollama=True,
        )
        if not (reply or "").strip():
            return None
        response = _build_llm_fallback_response(
            reply=reply,
            agent_type=agent_type,
            intent=intent,
            llm_provider=provider,
            knowledge_hits=kb_hits,
        )
        footnote = _degraded_user_footnote(llm_failure)
        if footnote:
            response["reply"] = f"{response['reply']}{footnote}"
        response["llm_degraded"] = True
        logger.info(
            "Copilot admin — repli %s après échec Gemini (%s)",
            provider or "ollama",
            llm_failure,
        )
        return response
    except Exception as exc:
        err = str(exc).lower()
        if "timeout" in err or "timed out" in err:
            logger.warning("Ollama copilot admin timeout — repli local/déterministe")
        else:
            logger.warning("Repli Ollama copilot admin échoué (%s)", exc)
        return None


def _try_language_preference_reply(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_type: str,
    context: str,
    hist_text: str | None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    attached_document_name: str | None = None,
) -> dict[str, Any] | None:
    """Relance « réponds en français » — sans repasser par la boucle outils Gemini."""
    from app.services.gpt.memory_service import detect_language_preference

    pref = detect_language_preference(message)
    if not pref:
        return None

    lang_labels = {"fr": "français", "en": "anglais", "ar": "arabe"}
    label = lang_labels.get(pref, pref)
    if hist_text and hist_text.strip():
        task = (
            f"L'administrateur demande une réponse en {label}. "
            f"Reformule en {label} le contenu utile de ta dernière réponse dans CONVERSATION_HISTORY, "
            f"sans inventer de données. Garde les mêmes faits et chiffres."
        )
    else:
        task = (
            f"L'administrateur souhaite communiquer en {label}. "
            f"Confirme en {label} que vous répondrez en {label} pour la suite."
        )

    try:
        reply, intent, provider, kb_hits = _admin_copilot_llm_fallback(
            db,
            admin,
            task,
            context=context,
            hist_text=hist_text or "",
            agent_type=agent_type,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
        )
        return _build_llm_fallback_response(
            reply=reply,
            agent_type=agent_type,
            intent=intent,
            llm_provider=provider,
            knowledge_hits=kb_hits,
        )
    except Exception:
        logger.exception("Repli langue échoué pour %s", pref)
        return _build_llm_fallback_response(
            reply=(
                f"D'accord, je répondrai en {label} pour la suite. "
                "Le moteur IA est momentanément indisponible — réessayez dans quelques instants."
            ),
            agent_type=agent_type,
            intent="language_preference",
            llm_provider=None,
            knowledge_hits=0,
        )


def _try_deterministic_copilot_routes(
    db: Session,
    admin: User,
    task: str,
    *,
    agent_type: str,
    context: str = "",
    hist_text: str | None = None,
    agent_mode: bool = False,
    humanize: bool = True,
    force_degraded: bool = False,
    copilot_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Filet de sécurité sans LLM — users, tracking, notifications, tickets, logs."""
    if re.search(r"\b(tracking|exp[eé]ditions?|colis|shipments?)\b", (task or "").lower()):
        if _is_simple_tracking_list_query(task):
            tracking_first = _try_deterministic_admin_tracking(
                db, admin, task, agent_type=agent_type, humanize=humanize,
                force_degraded=force_degraded,
            )
            if tracking_first:
                return tracking_first
    return (
        _try_deterministic_admin_users(
            db, admin, task, agent_type=agent_type, context=context,
            conversation_history=hist_text,
            force_degraded=force_degraded,
            copilot_state=copilot_state,
        )
        or _try_deterministic_admin_tracking(
            db, admin, task, agent_type=agent_type, humanize=humanize,
            force_degraded=force_degraded,
        )
        or _try_deterministic_admin_notifications(
            db, admin, task, agent_type=agent_type,
            force_degraded=force_degraded,
            copilot_state=copilot_state,
        )
        or _try_deterministic_admin_conversations(
            db, admin, task, agent_type=agent_type,
            force_degraded=force_degraded,
        )
        or _try_deterministic_admin_tickets(
            db, admin, task, agent_type=agent_type,
            force_degraded=force_degraded,
        )
        or _try_deterministic_admin_logs(
            db, admin, task, agent_type=agent_type, conversation_history=hist_text,
            force_degraded=force_degraded,
        )
    )


def _llm_unavailable_reply() -> str:
    return _engine_unavailable_reply()


def _admin_copilot_llm_fallback(
    db: Session,
    admin: User,
    task: str,
    *,
    context: str,
    hist_text: str,
    agent_type: str,
    ui_language: str = "fr",
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    attached_document_name: str | None = None,
    fast_ollama: bool = False,
) -> tuple[str, str | None, str | None, int]:
    """Repli admin — jamais le prompt client FedEx."""
    if fast_ollama or is_global_gemini_quota_exhausted():
        out = generate_ollama_admin_fast(
            task,
            context=context,
            conversation_history=hist_text,
            ui_language=ui_language,
            max_output_tokens=200,
        )
        return out.reply, agent_type, out.llm_provider, 0

    try:
        turn = run_gpt_turn(
            db,
            gpt_slug=SLUG_ADMIN,
            user_id=admin.id,
            message=task,
            ui_language=ui_language,
            profile_language=ui_language,
            operational_context=context,
            conversation_history=hist_text,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
        )
        return turn.reply, turn.intent or agent_type, turn.llm_provider, len(turn.knowledge_sources)
    except Exception as exc:
        if _llm_failure_reason(exc) in ("quota", "overload") or "timeout" in str(exc).lower():
            logger.warning("run_gpt_turn indisponible — repli Ollama rapide admin")
        else:
            logger.warning("run_gpt_turn échoué — repli generate_with_context admin : %s", exc)
        out = generate_ollama_admin_fast(
            task,
            context=context,
            conversation_history=hist_text,
            ui_language=ui_language,
            max_output_tokens=200,
        )
        return out.reply, agent_type, out.llm_provider, 0


def run_admin_copilot_analysis(
    db: Session,
    admin: User,
    message: str,
    *,
    quick_action: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    copilot_state: dict[str, Any] | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    attached_document_name: str | None = None,
) -> dict[str, Any]:
    """Mode analyse — moteur Gemini + READ TOOLS ; repli déterministe si LLM indisponible."""
    blocked = _copilot_security_block(admin, message)
    if blocked:
        return blocked

    context = _build_operational_context(db)
    task = _enrich_task_with_attachment(resolve_copilot_message(message, quick_action), attached_document_name)
    agent_type = detect_copilot_agent_type(task, quick_action)
    hist_text = format_copilot_history(conversation_history)
    ui_lang = _resolve_copilot_language(
        admin, task, session_language=(copilot_state or {}).get("preferred_language"),
    )
    settings = get_settings()

    greeting = None  # Salutations → Gemini (pas de regex / template)
    if greeting:
        return greeting

    context = _merge_state_instruction(context, copilot_state, conversation_history)

    pre_llm = _try_pre_llm_admin_routes(
        db,
        admin,
        task,
        agent_type=agent_type,
        agent_mode=False,
        lang=ui_lang,
        context=context,
        hist_text=hist_text,
        copilot_state=copilot_state,
        conversation_history=conversation_history,
    )
    if pre_llm:
        pre_llm.setdefault("language", ui_lang)
        return pre_llm

    lang_reply = _try_language_preference_reply(
        db,
        admin,
        task,
        agent_type=agent_type,
        context=context,
        hist_text=hist_text,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
        attached_document_name=attached_document_name,
    )
    if lang_reply:
        return lang_reply

    contextual = _try_conversation_context_turn(
        db, admin, task,
        conversation_history=conversation_history,
        copilot_state=copilot_state,
        agent_mode=False,
        agent_type=agent_type,
        ui_lang=ui_lang,
    )
    if contextual:
        return contextual

    llm_failure: str | None = None
    if not _admin_copilot_uses_jarvis():
        if not gemini_api_key_usable():
            llm_failure = "auth"
        elif is_global_gemini_quota_exhausted():
            llm_failure = "quota"

    try:
        from app.services.ai_assistant.admin_ai_service import AdminAiService

        return AdminAiService.run_turn(
            db,
            admin,
            task,
            analysis_mode=True,
            operational_context=context,
            conversation_history=conversation_history,
            copilot_state=copilot_state,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
            agent_type=agent_type,
        )
    except Exception as exc:
        llm_failure = _log_gemini_agent_failure(exc, context_label="analyse") or llm_failure

    if llm_failure == "auth":
        return _build_analysis_unavailable_response(agent_type=agent_type, reason=llm_failure)

    if llm_failure:
        from app.services.ai_assistant.copilot_pipeline import try_copilot_pipeline

        pipeline = try_copilot_pipeline(
            db, admin, task,
            copilot_state=copilot_state,
            conversation_history=conversation_history,
            agent_type=agent_type,
        )
        if pipeline:
            from app.services.ai_assistant.response_builder import enrich_copilot_response

            pipeline["llm_degraded"] = True
            return enrich_copilot_response(pipeline)
        emergency = _try_emergency_local_reply(
            task,
            agent_type=agent_type,
            agent_mode=False,
            lang=ui_lang,
            llm_failure=llm_failure,
        )
        if emergency:
            emergency["llm_degraded"] = True
            return emergency
        if llm_failure in ("quota", "overload"):
            ollama = _try_ollama_copilot_fallback(
                db,
                admin,
                task,
                context=context,
                hist_text=hist_text,
                agent_type=agent_type,
                ui_language=ui_lang,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
                attached_document_name=attached_document_name,
                llm_failure=llm_failure,
            )
            if ollama:
                return ollama
        emergency = _try_deterministic_copilot_routes(
            db, admin, task, agent_type=agent_type, context=context,
            hist_text=hist_text, agent_mode=False,
            humanize=True,
            force_degraded=True,
        )
        if emergency:
            emergency["llm_degraded"] = True
            return emergency
        if llm_failure not in ("quota", "overload"):
            ollama = _try_ollama_copilot_fallback(
                db,
                admin,
                task,
                context=context,
                hist_text=hist_text,
                agent_type=agent_type,
                ui_language=ui_lang,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
                attached_document_name=attached_document_name,
                llm_failure=llm_failure,
            )
            if ollama:
                return ollama
        return _build_analysis_unavailable_response(agent_type=agent_type, reason=llm_failure)

    try:
        reply, intent, provider, kb_hits = _admin_copilot_llm_fallback(
            db,
            admin,
            task,
            context=context,
            hist_text=hist_text,
            agent_type=agent_type,
            ui_language=ui_lang,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
        )
        return _build_llm_fallback_response(
            reply=reply,
            agent_type=agent_type,
            intent=intent,
            llm_provider=provider,
            knowledge_hits=kb_hits,
        )
    except Exception as exc:
        if not llm_failure:
            llm_failure = _llm_failure_reason(exc)
        logger.exception("Repli LLM texte admin échoué")
        ollama = _try_ollama_copilot_fallback(
            db,
            admin,
            task,
            context=context,
            hist_text=hist_text,
            agent_type=agent_type,
            ui_language=ui_lang,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
            llm_failure=llm_failure,
        )
        if ollama:
            return ollama

    return _build_analysis_unavailable_response(agent_type=agent_type, reason=llm_failure)


def run_admin_copilot_query(
    db: Session,
    admin: User,
    message: str,
    *,
    quick_action: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    copilot_state: dict[str, Any] | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    attached_document_name: str | None = None,
) -> dict[str, Any]:
    """Exécute une requête copilot admin — Phase 2 : Gemini tools ou runtime missions."""
    blocked = _copilot_security_block(admin, message)
    if blocked:
        return blocked

    task = _enrich_task_with_attachment(resolve_copilot_message(message, quick_action), attached_document_name)
    agent_type = detect_copilot_agent_type(task, quick_action)
    settings = get_settings()
    hist_text = format_copilot_history(conversation_history)
    ui_lang = _resolve_copilot_language(
        admin, task, session_language=(copilot_state or {}).get("preferred_language"),
    )
    has_image = bool((image_base64 or "").strip())

    greeting = None  # Salutations → Gemini (pas de regex / template)
    if greeting:
        greeting["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
        return greeting

    context = _build_operational_context(db)
    pre_llm = _try_pre_llm_admin_routes(
        db,
        admin,
        task,
        agent_type=agent_type,
        agent_mode=True,
        lang=ui_lang,
        context=context,
        hist_text=hist_text,
        copilot_state=copilot_state,
        conversation_history=conversation_history,
    )
    if pre_llm:
        pre_llm["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
        pre_llm.setdefault("language", ui_lang)
        return pre_llm

    contextual = _try_conversation_context_turn(
        db, admin, task,
        conversation_history=conversation_history,
        copilot_state=copilot_state,
        agent_mode=True,
        agent_type=agent_type,
        ui_lang=ui_lang,
    )
    if contextual:
        contextual["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
        return contextual

    if has_image and not attached_document_name:
        return run_admin_copilot_analysis(
            db,
            admin,
            message,
            quick_action=quick_action,
            conversation_history=conversation_history,
            copilot_state=copilot_state,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
        )

    query_llm_failure: str | None = None
    if not _admin_copilot_uses_jarvis():
        if not gemini_api_key_usable():
            query_llm_failure = "auth"
        elif is_global_gemini_quota_exhausted():
            query_llm_failure = "quota"

    stats_ctx = build_command_center(db)
    operational = (
        f"Contexte Globex Super Admin: "
        f"utilisateurs actifs={stats_ctx.hero_stats[2].value}, "
        f"expéditions aujourd'hui={stats_ctx.hero_stats[0].value}, "
        f"incidents ouverts={stats_ctx.open_incidents}, "
        f"requêtes FedEx aujourd'hui={stats_ctx.fedex_metrics.requests_today}."
    )
    operational = _merge_state_instruction(
        operational, copilot_state, conversation_history,
    )

    try:
        from app.services.ai_assistant.admin_ai_service import AdminAiService

        response = AdminAiService.run_turn(
            db,
            admin,
            task,
            analysis_mode=False,
            operational_context=operational,
            conversation_history=conversation_history,
            copilot_state=copilot_state,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            attached_document_name=attached_document_name,
            agent_type=agent_type,
        )
        response["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
        return response
    except Exception as exc:
        query_llm_failure = _log_gemini_agent_failure(exc, context_label="agent") or query_llm_failure

    if query_llm_failure == "auth":
        resp = _build_analysis_unavailable_response(agent_type=agent_type, reason=query_llm_failure)
        resp["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
        return resp

    if query_llm_failure:
        emergency = _try_emergency_local_reply(
            task,
            agent_type=agent_type,
            agent_mode=True,
            lang=ui_lang,
            llm_failure=query_llm_failure,
        )
        if emergency:
            emergency["llm_degraded"] = True
            emergency["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
            return emergency
        operational = _merge_state_instruction("", copilot_state, conversation_history)
        if query_llm_failure in ("quota", "overload"):
            ollama = _try_ollama_copilot_fallback(
                db,
                admin,
                task,
                context=operational,
                hist_text=hist_text,
                agent_type=agent_type,
                ui_language=ui_lang,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
                attached_document_name=attached_document_name,
                llm_failure=query_llm_failure,
            )
            if ollama:
                ollama["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
                return ollama
        emergency = _try_deterministic_copilot_routes(
            db, admin, task, agent_type=agent_type, context="",
            hist_text=hist_text, agent_mode=True, humanize=True,
            force_degraded=True,
        )
        if emergency:
            emergency["llm_degraded"] = True
            emergency["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
            return emergency
        if query_llm_failure not in ("quota", "overload"):
            ollama = _try_ollama_copilot_fallback(
                db,
                admin,
                task,
                context=operational,
                hist_text=hist_text,
                agent_type=agent_type,
                ui_language=ui_lang,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
                attached_document_name=attached_document_name,
                llm_failure=query_llm_failure,
            )
            if ollama:
                ollama["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
                return ollama
        resp = _build_analysis_unavailable_response(agent_type=agent_type, reason=query_llm_failure)
        resp["agent_type_label"] = AGENT_LABELS.get(agent_type, agent_type)
        return resp

    return _run_admin_copilot_mission_legacy(
        db, admin, task, agent_type=agent_type,
    )


def _run_admin_copilot_mission_legacy(
    db: Session,
    admin: User,
    task: str,
    *,
    agent_type: str,
) -> dict[str, Any]:
    """Runtime Agent Missions historique (repli)."""
    mission = AgentMission(
        admin_id=admin.id,
        agent_type=agent_type,
        task_description=task,
        status="running",
        schedule_type="now",
        plan_json=_safe_json_dumps({"type": "copilot", "source": "ai_assistant"}),
        require_approval_sensitive=True,
        notify_on_start=False,
        notify_on_complete=False,
        max_items=50,
        max_duration_minutes=15,
        started_at=_now(),
    )
    db.add(mission)
    db.flush()

    step = AgentMissionStep(
        mission_id=mission.id,
        step_order=1,
        title=f"Jarvis — {AGENT_LABELS.get(agent_type, agent_type)}",
        description=task[:500],
        action_type="copilot_execute",
        is_sensitive=False,
        status="running",
        started_at=_now(),
    )
    db.add(step)
    db.flush()

    context = _enrich_mission_context(db, mission, _gather_mission_context(db, mission))
    output = execute_admin_mission_task(
        db,
        mission,
        step,
        task=task,
        actor_admin_id=admin.id,
        require_approval=mission.require_approval_sensitive,
        approved=False,
        context=context,
    )
    _handle_step_output(db, mission, step, output)

    if output.get("needs_clarification"):
        mission.status = "pending"
        step.status = "waiting_input"
    elif step.status == "completed":
        mission.status = "completed"
        mission.finished_at = _now()
    elif step.status == "waiting_approval":
        mission.status = "waiting_permission"
    mission.updated_at = _now()

    approval_id: int | None = None
    if output.get("needs_approval"):
        pending = db.scalar(
            select(AgentApprovalRequest)
            .where(
                AgentApprovalRequest.mission_id == mission.id,
                AgentApprovalRequest.status == "pending",
            )
            .order_by(AgentApprovalRequest.id.desc())
        )
        if pending:
            approval_id = pending.id

    db.commit()

    reasoning = output.get("agent_reasoning") if isinstance(output.get("agent_reasoning"), dict) else {}
    return {
        "reply": str(output.get("task_answer") or output.get("analysis") or ""),
        "intent": str(output.get("action") or output.get("intent") or agent_type),
        "agent_type": agent_type,
        "agent_type_label": AGENT_LABELS.get(agent_type, agent_type),
        "mission_id": mission.id,
        "action_executed": bool(output.get("action_executed")),
        "needs_approval": bool(output.get("needs_approval")),
        "approval_id": approval_id,
        "analysis_only": bool(output.get("analysis_only")),
        "agent_steps": output.get("agent_steps") if isinstance(output.get("agent_steps"), list) else [],
        "agent_reasoning": reasoning,
        "conversation_id": mission.id,
        "export_download": output.get("export_download"),
        "agent_questionnaire": output.get("agent_questionnaire"),
        "llm_degraded": bool(output.get("llm_degraded")),
        "llm_provider": output.get("llm_provider"),
        "gpt_slug": None,
        "knowledge_hits": 0,
        "tools_used": [],
    }
