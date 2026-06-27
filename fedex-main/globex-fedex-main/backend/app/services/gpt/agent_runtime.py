"""Runtime agent GPT Phase 2 — Gemini function calling + exécution outils."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.gpt_definition import GptDefinition
from app.models.user import User
from app.services.gpt.follow_up_context import expand_follow_up_message
from app.services.gpt.knowledge_service import (
    build_attachment_context,
    format_knowledge_block,
    retrieve_knowledge,
)
from app.services.gpt.memory_service import (
    build_memory_context,
    detect_language_preference,
    format_memory_block,
    update_language_preference,
)
from app.services.gpt.prompt_composer import build_gpt_user_payload
from app.services.gpt.prompts import admin_gpt_system_for_lang, client_gpt_system_for_lang
from app.services.gpt.admin_reasoning_engine import (
    build_admin_reasoning_prompt,
    filter_tools_for_admin_mode,
    no_data_access_message,
)
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_registry import (
    gemini_tool_declarations,
    list_tools_for_gpt,
    ollama_tool_declarations,
)
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext
from app.services.gpt.orchestrator import (
    GptTurnResult,
    SLUG_ADMIN,
    _classify_intent,
    load_gpt_by_slug,
)
from app.services.llm.providers import (
    LlmProviderError,
    gemini_api_key_usable,
    gemini_tool_agent_loop,
    ollama_tool_agent_loop,
    normalize_lang_code,
    resolve_ui_language,
)

logger = logging.getLogger(__name__)

_GENERIC_CAPABILITIES = re.compile(
    r"(voici ce que je peux faire|je suis le \*\*copilot super admin)",
    re.I,
)
_FALSE_INJECTION = re.compile(
    r"prompt injection|cannot follow this instruction",
    re.I,
)

AGENT_TOOLS_SYSTEM_APPEND = """
MODE AGENT — lecture + actions :
- Utilisez les outils pour obtenir des données réelles avant de répondre.
- Ne inventez jamais de chiffres, statuts ou comptes.
- Après les résultats d'outils, synthétisez en prose professionnelle.
- Actions sensibles : le serveur demandera une approbation admin si nécessaire.
- Relances : lisez CONVERSATION_HISTORY et poursuivez le sujet précédent.
"""


def _run_tool_agent_loop(
    *,
    system_instruction: str,
    user_payload: str,
    gemini_declarations: list[dict[str, Any]],
    ollama_declarations: list[dict[str, Any]],
    on_tool_call: Any,
    max_rounds: int,
    max_output_tokens: int,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
) -> tuple[str, list[str], str]:
    """Boucle outils : Ollama en priorité si configuré, Gemini en secours."""
    settings = get_settings()
    primary = (settings.llm_primary_provider or "ollama").strip().lower()
    has_image = bool((image_base64 or "").strip())
    ollama_first = primary == "ollama" or (not gemini_api_key_usable() and not has_image)

    if has_image and gemini_api_key_usable():
        try:
            reply, tools_used = gemini_tool_agent_loop(
                system_instruction=system_instruction,
                user_payload=user_payload,
                tool_declarations=gemini_declarations,
                on_tool_call=on_tool_call,
                max_rounds=max_rounds,
                max_output_tokens=max_output_tokens,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
            )
            return reply, tools_used, "gemini"
        except Exception as exc:
            logger.warning("Gemini tool loop (image) failed: %s", exc)

    if ollama_first and not has_image:
        try:
            reply, tools_used = ollama_tool_agent_loop(
                system_instruction=system_instruction,
                user_payload=user_payload,
                tool_declarations=ollama_declarations,
                on_tool_call=on_tool_call,
                max_rounds=max_rounds,
                max_output_tokens=max_output_tokens,
            )
            return reply, tools_used, "ollama"
        except Exception as exc:
            logger.warning("Ollama tool loop failed: %s", exc)
            if gemini_api_key_usable():
                reply, tools_used = gemini_tool_agent_loop(
                    system_instruction=system_instruction,
                    user_payload=user_payload,
                    tool_declarations=gemini_declarations,
                    on_tool_call=on_tool_call,
                    max_rounds=max_rounds,
                    max_output_tokens=max_output_tokens,
                    image_base64=image_base64,
                    image_mime_type=image_mime_type,
                )
                return reply, tools_used, "gemini"
            raise

    try:
        reply, tools_used = gemini_tool_agent_loop(
            system_instruction=system_instruction,
            user_payload=user_payload,
            tool_declarations=gemini_declarations,
            on_tool_call=on_tool_call,
            max_rounds=max_rounds,
            max_output_tokens=max_output_tokens,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
        return reply, tools_used, "gemini"
    except Exception as exc:
        logger.warning("Gemini tool loop failed: %s", exc)
        if has_image:
            raise LlmProviderError("Boucle outils Gemini indisponible (image).") from exc
        reply, tools_used = ollama_tool_agent_loop(
            system_instruction=system_instruction,
            user_payload=user_payload,
            tool_declarations=ollama_declarations,
            on_tool_call=on_tool_call,
            max_rounds=max_rounds,
            max_output_tokens=max_output_tokens,
        )
        return reply, tools_used, "ollama"


@dataclass
class GptAgentTurnResult(GptTurnResult):
    tools_used: list[str] = field(default_factory=list)
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    agent_steps: list[dict[str, Any]] = field(default_factory=list)
    action_executed: bool = False
    needs_approval: bool = False
    export_download: dict[str, Any] | None = None


def enforce_french_reply(
    reply: str,
    *,
    lang: str,
    task: str,
    tool_payloads: list[dict[str, Any]] | None = None,
) -> str:
    """Force le français si Gemini répond en anglais sur une session FR."""
    if lang != "fr" or not (reply or "").strip():
        return reply or ""
    english_markers = re.compile(
        r"\b("
        r"I cannot|I can provide|This functionality|not available|"
        r"prompt injection|cannot follow this instruction|"
        r"here are your|the following|however|unfortunately"
        r")\b",
        re.I,
    )
    if not english_markers.search(reply):
        return reply
    from app.services.gpt.tool_synthesis import synthesize_admin_tool_turn

    if tool_payloads:
        synthesized = synthesize_admin_tool_turn(
            task=task,
            tool_payloads=tool_payloads,
            ui_language="fr",
        )
        if synthesized and not english_markers.search(synthesized):
            return synthesized
    if re.search(r"prompt injection|cannot follow", reply, re.I):
        return (
            "Je traite votre demande à partir des données réelles de la plateforme. "
            "Précisez si besoin le module (notifications, tracking, logs, utilisateurs)."
        )
    return reply


def run_gpt_agent_turn(
    db: Session,
    *,
    gpt_slug: str,
    user: User,
    message: str,
    session_id: int | None = None,
    ui_language: str | None = None,
    operational_context: str | None = None,
    fedex_context: str | None = None,
    response_preferences: str | None = None,
    preferred_name: str | None = None,
    conversation_history: str | None = None,
    analysis_mode: bool = False,
    attached_document_name: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    server_instruction: str | None = None,
    session_tracking_number: str | None = None,
) -> GptAgentTurnResult:
    """Tour agent complet : RAG → mémoire → Gemini + boucle outils."""
    settings = get_settings()
    gpt = load_gpt_by_slug(db, gpt_slug)
    if gpt is None:
        raise ValueError(f"GPT introuvable : {gpt_slug}")

    lang = resolve_ui_language(ui_language, user.preferred_language)
    pref_lang = detect_language_preference(message)
    if pref_lang:
        lang = pref_lang
        update_language_preference(db, user_id=user.id, gpt_id=gpt.id, language=lang)

    memory_ctx = build_memory_context(
        db, gpt=gpt, user_id=user.id, session_id=session_id,
    )
    facts = memory_ctx.get("long_facts") or {}
    if facts.get("preferred_response_language"):
        lang = normalize_lang_code(facts["preferred_response_language"])

    intent = _classify_intent(message, gpt_slug)
    intent_hint = f"INDICE_INTENTION (non contraignant) : {intent}"
    effective_message = expand_follow_up_message(message, conversation_history)
    rag_query = effective_message
    if attached_document_name:
        rag_query = f"{attached_document_name} {rag_query}"
    if (conversation_history or "").strip() and len((message or "").strip()) < 120:
        rag_query = f"{conversation_history.strip()[-800:]}\n{message}"
    if intent == "capabilities":
        rag_query = f"{message} capacités copilot globex"

    if intent == "admin_agents" and gpt_slug.startswith("fedex-admin"):
        from app.services.admin_copilot_service import build_agent_catalog_context

        operational_context = (
            (operational_context or "")
            + "\n\n"
            + build_agent_catalog_context()
            + "\n\nCONSIGNE SERVEUR : l'utilisateur demande les agents copilot disponibles "
            "et le rôle de chacun. Répondez DIRECTEMENT : nommez chaque agent et décrivez "
            "son rôle précis à partir du catalogue ci-dessus. Style professionnel et concis. "
            "INTERDIT : introduction « Je suis le Copilot » ou liste générique de capacités "
            "sans nommer les agents. Aucun outil plateforme nécessaire."
        )

    elif intent == "capabilities" and gpt_slug.startswith("fedex-admin"):
        operational_context = (
            (operational_context or "")
            + "\n\nCONSIGNE SERVEUR : question sur vos capacités générales. "
            "Répondez DIRECTEMENT en prose naturelle — pas de template « Voici ce que je peux faire » "
            "ni d'introduction « Je suis le Copilot ». Couvrez brièvement les domaines utiles. "
            "Aucun outil nécessaire."
        )

    hits = retrieve_knowledge(
        db, gpt=gpt, query=rag_query, language=lang,
        top_k=5 if attached_document_name else 3,
        min_score=0.35 if attached_document_name else (0.5 if intent == "capabilities" else 1.0),
    )

    attached_file_content, attachment_instruction = build_attachment_context(
        db,
        gpt=gpt,
        filename=attached_document_name,
        user_message=message,
    )
    merged_server_instruction = "\n\n".join(
        part.strip() for part in (attachment_instruction, server_instruction) if part and part.strip()
    ) or None

    payload = build_gpt_user_payload(
        effective_message,
        knowledge_text=format_knowledge_block(hits),
        memory_text=format_memory_block(memory_ctx),
        operational_context=(
            f"{operational_context or ''}\n\n{intent_hint}".strip()
            if gpt_slug.startswith("fedex-admin")
            else intent_hint if gpt_slug.startswith("fedex-client") else operational_context
        ),
        fedex_context=fedex_context,
        response_preferences=response_preferences,
        preferred_name=preferred_name,
        ui_language=lang,
        conversation_history=conversation_history,
        server_instruction=merged_server_instruction,
        attached_file_content=attached_file_content or None,
    )

    role = (user.role or "client").lower()
    tools = list_tools_for_gpt(gpt, user_role=role)
    if gpt_slug.startswith("fedex-admin"):
        tools = filter_tools_for_admin_mode(tools, analysis_mode=analysis_mode)
    declarations = gemini_tool_declarations(tools)
    ollama_declarations = ollama_tool_declarations(tools)

    system = (
        admin_gpt_system_for_lang(lang)
        if gpt_slug.startswith("fedex-admin")
        else client_gpt_system_for_lang(lang)
    )
    if gpt_slug.startswith("fedex-admin"):
        reasoning = build_admin_reasoning_prompt(analysis_mode=analysis_mode, lang=lang)
        mode_append = f"{AGENT_TOOLS_SYSTEM_APPEND}\n\n{reasoning}"
    else:
        mode_append = AGENT_TOOLS_SYSTEM_APPEND
    system = f"{system}\n\n{mode_append}"

    tool_ctx = ToolExecutionContext(
        db=db,
        user_id=user.id,
        user_role=role,
        gpt_slug=gpt_slug,
        actor_admin_id=user.id if role == "admin" else None,
        ui_language=lang,
        analysis_mode=analysis_mode and gpt_slug.startswith("fedex-admin"),
        session_id=session_id,
    )

    agent_steps: list[dict[str, Any]] = []
    side_effects: dict[str, Any] = {
        "action_executed": False,
        "needs_approval": False,
        "export_download": None,
    }
    tool_payloads: list[dict[str, Any]] = []

    def _on_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        agent_steps.append({"label": name, "status": "running", "detail": json.dumps(args, ensure_ascii=False)[:200]})
        result = execute_tool(tool_ctx, ToolCall(name=name, args=args))
        tool_payloads.append({"name": name, "response": result.to_function_response()})
        if result.needs_approval:
            side_effects["needs_approval"] = True
            agent_steps.append({"label": name, "status": "warning", "detail": "Approbation requise"})
        elif result.success:
            agent_steps.append({"label": name, "status": "done", "detail": None})
            if result.data.get("action_executed"):
                side_effects["action_executed"] = True
            if result.data.get("export_download"):
                side_effects["export_download"] = result.data["export_download"]
                side_effects["action_executed"] = True
        else:
            agent_steps.append({"label": name, "status": "error", "detail": result.error})
        return result.to_function_response()

    reply, tools_used, llm_provider = _run_tool_agent_loop(
        system_instruction=system,
        user_payload=payload,
        gemini_declarations=declarations,
        ollama_declarations=ollama_declarations,
        on_tool_call=_on_tool,
        max_rounds=(
            max(settings.gpt_tool_max_rounds, 6)
            if analysis_mode and gpt_slug.startswith("fedex-admin")
            else settings.gpt_tool_max_rounds
        ),
        max_output_tokens=max(gpt.max_output_tokens, 2048),
        image_base64=image_base64,
        image_mime_type=image_mime_type,
    )

    if gpt_slug.startswith("fedex-admin"):
        from app.services.admin_copilot_service import (
            _requires_platform_data_tools,
        )
        from app.services.gpt.tool_synthesis import (
            all_tools_failed,
            synthesize_admin_tool_turn,
        )

        kb_count = len(hits)
        if _requires_platform_data_tools(
            message, intent, knowledge_hits=kb_count,
        ) and not tools_used:
            reply = no_data_access_message(lang)
        elif tools_used and all_tools_failed(tool_payloads):
            reply = (
                "L'information n'a pas pu être récupérée."
                if lang == "fr"
                else "The information could not be retrieved."
            )
        elif tools_used:
            # Règle fondamentale : les outils = données JSON ; Gemini = seule voix utilisateur.
            synthesized = synthesize_admin_tool_turn(
                task=message,
                tool_payloads=tool_payloads,
                ui_language=lang,
            )
            if synthesized:
                reply = synthesized
            elif not (reply or "").strip():
                reply = no_data_access_message(lang)

        if _FALSE_INJECTION.search(reply or "") and tools_used:
            synthesized = synthesize_admin_tool_turn(
                task=message,
                tool_payloads=tool_payloads,
                ui_language=lang,
            )
            if synthesized and not _FALSE_INJECTION.search(synthesized):
                reply = synthesized
        if intent in ("admin_agents", "capabilities") and _GENERIC_CAPABILITIES.search(reply or ""):
            from app.services.admin_copilot_service import build_agent_catalog_context

            catalog = build_agent_catalog_context()
            synthesized = synthesize_admin_tool_turn(
                task=message,
                tool_payloads=[
                    {"name": "agent_catalog", "response": {"status": "ok", "catalog": catalog}},
                ],
                ui_language=lang,
            )
            if synthesized:
                reply = synthesized
        reply = enforce_french_reply(
            reply,
            lang=lang,
            task=message,
            tool_payloads=tool_payloads,
        )
    elif gpt_slug.startswith("fedex-client"):
        from app.services.gpt.tool_synthesis import (
            all_tools_failed,
            synthesize_client_tool_turn,
        )

        if tools_used or side_effects.get("export_download"):
            if tools_used and all_tools_failed(tool_payloads) and not side_effects.get("export_download"):
                if not (reply or "").strip():
                    reply = (
                        "Je n'ai pas pu récupérer les informations demandées."
                        if lang == "fr"
                        else "I could not retrieve the requested information."
                    )
            elif tools_used or side_effects.get("export_download"):
                synthesized = synthesize_client_tool_turn(
                    task=message,
                    tool_payloads=tool_payloads,
                    ui_language=lang,
                    preferred_name=preferred_name,
                )
                if synthesized:
                    reply = synthesized
        reply = enforce_french_reply(
            reply,
            lang=lang,
            task=message,
            tool_payloads=tool_payloads,
        )

    sources = [h.source_ref or h.title for h in hits if h.source_ref or h.title]

    return GptAgentTurnResult(
        reply=reply,
        llm_provider=llm_provider,
        gpt_slug=gpt_slug,
        knowledge_sources=sources,
        intent=intent,
        tools_used=tools_used,
        tool_payloads=tool_payloads,
        agent_steps=agent_steps,
        action_executed=bool(side_effects["action_executed"]),
        needs_approval=bool(side_effects["needs_approval"]),
        export_download=side_effects["export_download"],
    )
