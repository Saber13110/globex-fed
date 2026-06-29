"""Noyau Globex Agent — Ollama orchestre, outils = sources de données."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services.activity_log_service import write_log
from app.services.ai_assistant.tool_executor import build_tool_context
from app.services.ai_assistant.tool_planner import plan_export_tools
from app.services.ai_assistant.timeout_utils import run_with_timeout
from app.services.globex_agent.approval import create_tool_approval
from app.services.globex_agent.approval_policy import detect_admin_direct_order
from app.services.globex_agent.client_action_planner import (
    COMM_ACTION_TOOLS,
    enrich_send_args_from_search,
    filter_tools_for_client_communication,
    is_client_communication_action,
    plan_client_action_tools,
)
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.tracking_rescue import (
    build_tracking_error_kernel_result,
    try_admin_kernel_tracking_rescue,
)
from app.services.globex_agent.admin_action_bridge import try_admin_simple_actions
from app.services.globex_agent.admin_chat import admin_ollama_chat
from app.services.globex_agent.language import resolve_admin_chat_language
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number
from app.services.globex_agent.local_replies import (
    naturalize_tool_reply,
    ollama_unavailable_reply,
)
from app.services.globex_agent.ollama_readiness import ollama_inference_ready
from app.services.globex_agent.read_action_planner import plan_read_action_tools
from app.services.globex_agent.routers import plan_admin_platform_task, plan_to_tool_calls
from app.services.globex_agent.scan_action_planner import plan_scan_action_tools
from app.services.globex_agent.security_action_planner import plan_security_action_tools
from app.services.admin_agent_tools import find_user_for_task
from app.services.gpt.admin_reasoning_engine import filter_tools_for_admin_mode
from app.services.gpt.intent_classifier import classify_intent
from app.services.gpt.orchestrator import SLUG_ADMIN, load_gpt_by_slug
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_registry import list_tools_for_gpt
from app.services.gpt.tool_synthesis import synthesize_tool_results
from app.services.gpt.tool_types import ToolCall
from app.services.llm.providers import LlmProviderError

logger = logging.getLogger(__name__)

_FALSE_EXPORT_CLAIM_RE = re.compile(
    r"(je vous ai envoyé|j['']ai envoyé|pdf contenant|fichier joint|téléchargement en cours)",
    re.I,
)
_FAKE_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https?://[^\)]+\)",
    re.I,
)
_FAKE_HTTP_URL_RE = re.compile(
    r"https?://(?:www\.)?globexfedex\.com[^\s\)\]]*",
    re.I,
)
_FAKE_UI_MENU_RE = re.compile(
    r"(générateur de pdf|g[eé]n[eé]rateur de pdf|espace de gestion|"
    r"cliquez sur [«\"]|menu [«\"]outils|étapes à suivre\s*:|"
    r"connectez-vous à votre compte|sélectionnez [«\"]excel)",
    re.I,
)
_RAW_TOOL_DUMP_RE = re.compile(
    r"(Résultat\s+\w+\s*:|'status'\s*:\s*'ok'|\"status\"\s*:\s*\"ok\")",
    re.I,
)


def _sanitize_fake_links(reply: str) -> str:
    if not reply:
        return reply
    cleaned = _FAKE_MARKDOWN_LINK_RE.sub(r"\1", reply)
    cleaned = _FAKE_HTTP_URL_RE.sub("", cleaned)
    if _FAKE_UI_MENU_RE.search(cleaned):
        lines = [ln for ln in cleaned.splitlines() if not _FAKE_UI_MENU_RE.search(ln)]
        cleaned = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _sanitize_false_export_claims(reply: str, export_download: dict[str, Any] | None) -> str:
    reply = _sanitize_fake_links(reply)
    if export_download:
        return reply
    if not reply or not _FALSE_EXPORT_CLAIM_RE.search(reply):
        return reply
    lines = [ln for ln in reply.splitlines() if not _FALSE_EXPORT_CLAIM_RE.search(ln)]
    cleaned = "\n".join(lines).strip()
    if cleaned and cleaned != reply.strip():
        cleaned += (
            "\n\n_(Aucun fichier n'a été généré — demandez « exporte … en PDF » pour obtenir un téléchargement.)_"
        )
    return cleaned or reply


def _format_history(history: list[dict[str, str]] | None, max_turns: int = 8) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for item in history[-max_turns:]:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"{role.upper()}: {content[:500]}")
    return "\n".join(lines)


def _enrich_tool_args(
    db: Session,
    message: str,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    a = dict(args or {})
    if name in COMM_ACTION_TOOLS and not a.get("user_id"):
        user = find_user_for_task(db, message)
        if user:
            a.setdefault("user_id", user.id)
            a.setdefault("email", user.email)
    return a


def _humanize_action_with_ollama(
    *,
    message: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str,
    local_reply: str | None,
) -> tuple[str, bool]:
    """Reformule une confirmation d'action en prose naturelle (sans noms d'outils)."""
    base = (local_reply or "").strip()
    if not base:
        return base, True
    lang = (ui_language or "fr").lower()[:2]
    if not ollama_inference_ready():
        natural = naturalize_tool_reply(
            tool_payloads, message=message, lang=lang,
        )
        if natural:
            return natural, True
        return base, True
    try:
        from app.services.gpt.model_gateway import generate_ollama_admin_fast

        settings = get_settings()
        facts = json.dumps(tool_payloads, ensure_ascii=False, default=str)[:4000]
        prompt = (
            f"Demande admin : {message[:500]}\n\n"
            f"Faits (JSON interne) : {facts}\n\n"
            f"Confirmation factuelle : {base}\n\n"
            "Réécris une réponse courte (2-4 phrases), chaleureuse et professionnelle. "
            "Parle comme un collègue humain. Ne mentionne jamais de noms d'outils techniques."
        )
        timeout = float(
            settings.ai_llm_ollama_timeout_seconds or settings.ollama_timeout_seconds or 120,
        )

        def _ollama() -> str | None:
            out = generate_ollama_admin_fast(
                prompt,
                ui_language=ui_language,
                max_output_tokens=280,
            )
            return (out.reply or "").strip() or None

        human = run_with_timeout(_ollama, timeout_seconds=timeout, label="globex-humanize")
        if human and len(human) > 15 and not _RAW_TOOL_DUMP_RE.search(human):
            return human, False
    except Exception as exc:
        logger.debug("[GlobexAgent] humanize Ollama : %s", exc)
    natural = naturalize_tool_reply(
        tool_payloads, message=message, lang=(ui_language or "fr").lower()[:2],
    )
    if natural:
        return natural, False
    return base, False


def _fallback_reply(
    *,
    message: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str,
    llm_reply: str,
) -> tuple[str, bool]:
    """Secours si Ollama n'a pas produit de texte exploitable."""
    for item in tool_payloads:
        payload = item.get("response") if isinstance(item.get("response"), dict) else {}
        if payload.get("status") == "approval_required":
            return str(payload.get("message") or "Approbation requise."), False

    text = (llm_reply or "").strip()
    if text and len(text) > 10 and not _RAW_TOOL_DUMP_RE.search(text):
        return text, False

    local = synthesize_tool_results(tool_payloads, ui_language=ui_language)
    if local:
        return local, True

    lang = (ui_language or "fr").lower()[:2]
    if not ollama_inference_ready():
        natural = naturalize_tool_reply(
            tool_payloads, message=message, lang=lang,
        )
        if natural:
            return natural, True
        return ollama_unavailable_reply(lang=lang), True

    from app.services.gpt.model_gateway import generate_ollama_admin_fast

    settings = get_settings()
    context = json.dumps(tool_payloads, ensure_ascii=False, default=str)[:6000]

    def _ollama() -> str | None:
        out = generate_ollama_admin_fast(
            message,
            context=context,
            ui_language=ui_language,
            max_output_tokens=900,
        )
        return (out.reply or "").strip() or None

    timeout = float(settings.ai_llm_ollama_timeout_seconds or settings.ollama_timeout_seconds or 120)
    synthesized = run_with_timeout(_ollama, timeout_seconds=timeout, label="globex-synth")
    if synthesized:
        return synthesized, False

    lang = (ui_language or "fr").lower()[:2]
    if not ollama_inference_ready():
        return ollama_unavailable_reply(lang=lang), True
    return (
        "Je n'ai pas pu formuler une réponse. Réessayez ou précisez votre demande."
        if lang == "fr"
        else "I could not formulate a response. Please try again."
    ), True


def _build_final_reply(
    *,
    llm_reply: str,
    tool_payloads: list[dict[str, Any]],
    export_download: dict[str, Any] | None,
    needs_approval: bool,
    approval_hint: str | None,
    message: str,
    ui_language: str,
) -> tuple[str, bool]:
    degraded = False
    text = (llm_reply or "").strip()

    if needs_approval and approval_hint:
        hint_low = approval_hint.lower()
        if text and (approval_hint in text or hint_low in text.lower() or "approbation" in text.lower()):
            return text, False
        prefix = f"{text}\n\n" if text else ""
        return f"{prefix}{approval_hint}", False

    if export_download:
        fname = str(export_download.get("filename") or "export.pdf")
        if text and len(text) > 15 and not _RAW_TOOL_DUMP_RE.search(text):
            if fname not in text:
                text += f"\n\n📎 Fichier prêt : **{fname}**"
            return text, False
        fmt = str(export_download.get("format") or "pdf").lower()
        label = "Excel" if fmt == "xlsx" else "PDF"
        return (
            f"Export {label} prêt : **{fname}**.\nTéléchargez le fichier via le lien ci-dessous."
        ), True

    if text and len(text) > 3 and not _RAW_TOOL_DUMP_RE.search(text):
        return text, False

    reply, degraded = _fallback_reply(
        message=message,
        tool_payloads=tool_payloads,
        ui_language=ui_language,
        llm_reply=llm_reply,
    )
    return reply, degraded


def run_globex_agent_chat(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_mode: bool = False,
    conversation_history: list[dict[str, str]] | None = None,
    ui_language: str = "fr",
    ip_address: str = "",
    chat_session_id: int | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """
    Pipeline cascade client-like :
    P0 planifiers métier → P2 routeur JSON → P1 chat Ollama → P3 boucle outils réduite.
    """
    started = time.perf_counter()
    lang = resolve_admin_chat_language(message, ui_language)

    settings = get_settings()
    if settings.globex_simple_mode:
        # PHASE -1 — pipeline client (suivi/PDF/Excel/documents/notifications) ; None = poursuivre
        pipeline_result = run_admin_client_turn(
            db,
            admin,
            message,
            conversation_history=conversation_history,
            ui_language=lang,
            chat_session_id=chat_session_id,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            file_name=file_name,
            ip_address=ip_address,
            started=started,
        )
        if pipeline_result is not None:
            return pipeline_result

        # PHASE 0.5 — tracking/exports déterministes, puis Ollama si aucun match
        bridge_result = try_admin_simple_actions(
            db,
            admin,
            message,
            conversation_history=conversation_history,
            ui_language=lang,
            agent_mode=agent_mode,
            ip_address=ip_address,
            started=started,
        )
        if bridge_result is not None:
            return bridge_result

        rescue_result = try_admin_kernel_tracking_rescue(
            db,
            admin,
            message,
            conversation_history=conversation_history,
            ui_language=lang,
            chat_session_id=chat_session_id,
            ip_address=ip_address,
            started=started,
        )
        if rescue_result is not None:
            return rescue_result

        tn_guard = extract_tracking_number(message or "")
        if tn_guard and is_plausible_tracking_number(tn_guard):
            return build_tracking_error_kernel_result(
                message=message,
                ui_language=lang,
                admin=admin,
                ip_address=ip_address,
                started=started,
            )

        # PHASE 0 — Ollama seul. REACTIVER P0/P2/P1 : GLOBEX_SIMPLE_MODE=false
        llm_degraded = False
        tools_used: list[str] = []
        try:
            llm_reply = admin_ollama_chat(
                message,
                ui_language=lang,
                conversation_history=conversation_history,
                agent_mode=agent_mode,
            )
            tools_used.append("ollama_chat")
        except LlmProviderError as exc:
            logger.warning("[GlobexAgent] Phase 0 Ollama échec : %s", exc)
            llm_reply = ollama_unavailable_reply(lang=lang)
            tools_used.append("ollama_chat")
            llm_degraded = True

        elapsed = round((time.perf_counter() - started) * 1000, 1)
        write_log(
            db,
            action="globex_agent.chat",
            message=message[:120],
            category="admin",
            level="INFO",
            actor_user_id=admin.id,
            ip_address=ip_address,
            metadata={
                "agent_mode": agent_mode,
                "tools": tools_used,
                "orchestrator": "ollama_chat",
                "simple_mode": True,
            },
        )
        db.commit()
        return {
            "reply": llm_reply,
            "mode": "jarvis",
            "tools_used": tools_used,
            "agent_steps": [],
            "needs_approval": False,
            "approval_id": None,
            "approval_hint": None,
            "mission_id": None,
            "action_executed": False,
            "export_download": None,
            "llm_degraded": llm_degraded,
            "intent": "general_question",
            "execution_time_ms": elapsed,
        }

    # REACTIVER: GLOBEX_SIMPLE_MODE=false — pipeline P0 → P2 → P1 ci-dessous
    gpt = load_gpt_by_slug(db, SLUG_ADMIN)
    if gpt is None:
        raise RuntimeError("Configuration GPT admin introuvable.")

    admin_direct = bool(agent_mode and detect_admin_direct_order(message))
    tool_ctx = build_tool_context(
        db,
        admin,
        analysis_mode=not agent_mode,
        ui_language=lang,
        admin_direct_order=admin_direct,
    )
    role = (admin.role or "admin").lower()
    tools = filter_tools_for_admin_mode(
        list_tools_for_gpt(gpt, user_role=role),
        analysis_mode=not agent_mode,
    )
    client_action = agent_mode and is_client_communication_action(
        message, history=conversation_history,
    )
    if client_action:
        tools = filter_tools_for_client_communication(tools)
    classification = classify_intent(message, SLUG_ADMIN)

    agent_steps: list[dict[str, Any]] = []
    tool_payloads: list[dict[str, Any]] = []
    tools_used: list[str] = []
    needs_approval = False
    approval_id: int | None = None
    mission_id: int | None = None
    approval_hint: str | None = None
    export_download: dict[str, Any] | None = None
    action_executed = False

    hist_text = _format_history(conversation_history)

    def _on_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal needs_approval, approval_id, mission_id, approval_hint
        nonlocal export_download, action_executed
        if client_action and name.startswith("export_"):
            err = (
                "Refusé — cette demande est un envoi mail/notification, pas un export PDF. "
                "Utilise search_users puis send_client_email ou notify_user."
            )
            resp = {"status": "error", "error": err}
            tool_payloads.append({"name": name, "response": resp})
            if name not in tools_used:
                tools_used.append(name)
            return resp
        enriched = _enrich_tool_args(db, message, name, args)
        agent_steps.append({
            "label": name,
            "status": "running",
            "detail": json.dumps(enriched, ensure_ascii=False)[:120],
        })
        result = execute_tool(tool_ctx, ToolCall(name=name, args=enriched))
        resp = result.to_function_response()
        tool_payloads.append({"name": name, "response": resp})
        if name not in tools_used:
            tools_used.append(name)
        if result.needs_approval:
            needs_approval = True
            approval_hint = result.approval_hint
            aid, mid = create_tool_approval(
                db, admin, tool_name=name, args=enriched, hint=result.approval_hint,
            )
            approval_id = aid
            mission_id = mid
        elif result.success and result.data.get("export_download"):
            export_download = result.data["export_download"]
            action_executed = True
        elif result.success and result.data.get("action_executed"):
            action_executed = True
        agent_steps.append({
            "label": name,
            "status": "done" if result.success else "error",
            "detail": result.error,
        })
        return resp

    llm_reply = ""
    llm_degraded = False
    planned_tools = (
        plan_client_action_tools(message, conversation_history)
        if client_action
        else None
    )
    planned_scan = (
        plan_scan_action_tools(message)
        if agent_mode and not planned_tools
        else None
    )
    planned_security = (
        plan_security_action_tools(message)
        if agent_mode and not planned_tools and not planned_scan
        else None
    )
    planned_export = (
        plan_export_tools(message, conversation_history)
        if agent_mode and not planned_tools and not planned_scan and not planned_security and not client_action
        else None
    )
    planned_read = (
        plan_read_action_tools(message, classification.intent, conversation_history)
        if agent_mode and not planned_tools and not planned_scan and not planned_security and not planned_export
        else None
    )
    deterministic_comm = False
    deterministic_scan = False
    deterministic_security = False
    deterministic_export = False
    deterministic_read_plan = False

    if planned_tools:
        deterministic_comm = True
        for tool_name, tool_args in planned_tools:
            args = dict(tool_args or {})
            if tool_name in {"send_client_email", "notify_user", "send_email"}:
                args = enrich_send_args_from_search(args, tool_payloads)
            _on_tool(tool_name, args)
    elif planned_scan:
        deterministic_scan = True
        for tool_name, tool_args in planned_scan:
            _on_tool(tool_name, dict(tool_args or {}))
    elif planned_security:
        deterministic_security = True
        for tool_name, tool_args in planned_security:
            _on_tool(tool_name, dict(tool_args or {}))
    elif planned_export:
        deterministic_export = True
        for tool_name, tool_args in planned_export:
            _on_tool(tool_name, dict(tool_args or {}))
    elif planned_read:
        deterministic_read_plan = True
        for tool_name, tool_args in planned_read:
            _on_tool(tool_name, dict(tool_args or {}))

    deterministic_any = (
        deterministic_comm
        or deterministic_scan
        or deterministic_security
        or deterministic_export
        or deterministic_read_plan
    )
    orchestrator = "deterministic"

    if deterministic_any and tool_payloads:
        local = synthesize_tool_results(tool_payloads, ui_language=lang)
        if deterministic_scan or deterministic_security or deterministic_read_plan:
            llm_reply = local or ""
            llm_degraded = not bool(local)
        else:
            llm_reply, synth_degraded = _humanize_action_with_ollama(
                message=message,
                tool_payloads=tool_payloads,
                ui_language=lang,
                local_reply=local,
            )
            if not llm_reply:
                llm_reply, synth_degraded = _fallback_reply(
                    message=message,
                    tool_payloads=tool_payloads,
                    ui_language=lang,
                    llm_reply="",
                )
            if synth_degraded:
                llm_degraded = True
    elif not deterministic_any:
        platform_plan = plan_admin_platform_task(
            message,
            conversation_history=hist_text or None,
            ui_language=lang,
        )
        if platform_plan and platform_plan.get("needs_clarification") and platform_plan.get(
            "clarification_question",
        ):
            llm_reply = platform_plan["clarification_question"]
            tools_used.append("platform_router")
            orchestrator = "platform_router"
        elif platform_plan and platform_plan.get("ready_to_execute"):
            tools_used.append("platform_router")
            orchestrator = "platform_router"
            intro = platform_plan.get("assistant_intro") or ""
            for tool_name, tool_args in plan_to_tool_calls(platform_plan):
                _on_tool(tool_name, tool_args)
            local = synthesize_tool_results(tool_payloads, ui_language=lang)
            llm_reply = local or intro
            if tool_payloads:
                llm_reply, synth_degraded = _humanize_action_with_ollama(
                    message=message,
                    tool_payloads=tool_payloads,
                    ui_language=lang,
                    local_reply=llm_reply,
                )
                if synth_degraded:
                    llm_degraded = True
        else:
            try:
                llm_reply = admin_ollama_chat(
                    message,
                    ui_language=lang,
                    conversation_history=conversation_history,
                    agent_mode=agent_mode,
                )
                tools_used.append("ollama_chat")
                orchestrator = "ollama_chat"
            except LlmProviderError as exc:
                logger.warning("[GlobexAgent] admin_ollama_chat échec : %s", exc)
                llm_reply = ollama_unavailable_reply(lang=lang)
                tools_used.append("ollama_chat")
                orchestrator = "ollama_chat"
                llm_degraded = True

    if needs_approval and approval_id is None and tool_payloads:
        last = tool_payloads[-1]
        name = last.get("name", "action")
        resp = last.get("response") or {}
        if resp.get("status") == "approval_required":
            params = resp.get("parameters") or {}
            aid, mid = create_tool_approval(
                db,
                admin,
                tool_name=name,
                args=params if isinstance(params, dict) else {},
                hint=resp.get("message"),
            )
            approval_id = aid
            mission_id = mid

    final_reply, synth_degraded = _build_final_reply(
        llm_reply=llm_reply,
        tool_payloads=tool_payloads,
        export_download=export_download,
        needs_approval=needs_approval,
        approval_hint=approval_hint,
        message=message,
        ui_language=lang,
    )
    if synth_degraded:
        llm_degraded = True

    final_reply = _sanitize_false_export_claims(final_reply, export_download)
    elapsed = round((time.perf_counter() - started) * 1000, 1)

    write_log(
        db,
        action="globex_agent.chat",
        message=message[:120],
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=ip_address,
        metadata={
            "agent_mode": agent_mode,
            "tools": tools_used,
            "needs_approval": needs_approval,
            "intent": classification.intent,
            "orchestrator": orchestrator,
        },
    )
    db.commit()

    return {
        "reply": final_reply,
        "mode": "jarvis",
        "tools_used": tools_used,
        "agent_steps": agent_steps,
        "needs_approval": needs_approval,
        "approval_id": approval_id,
        "approval_hint": approval_hint,
        "mission_id": mission_id,
        "action_executed": action_executed,
        "export_download": export_download,
        "llm_degraded": llm_degraded,
        "intent": classification.intent,
        "execution_time_ms": elapsed,
    }


def execute_globex_tool(
    db: Session,
    admin: User,
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    agent_mode: bool = True,
    ui_language: str = "fr",
) -> dict[str, Any]:
    """Exécution directe d'un outil (debug / skill Jarvis)."""
    ctx = build_tool_context(
        db, admin, analysis_mode=not agent_mode, ui_language=ui_language,
    )
    result = execute_tool(ctx, ToolCall(name=tool_name, args=args or {}))
    resp = result.to_function_response()
    if result.needs_approval:
        aid, _ = create_tool_approval(
            db, admin, tool_name=tool_name, args=args or {}, hint=result.approval_hint,
        )
        db.commit()
        resp["approval_id"] = aid
    else:
        db.commit()
    return {
        "tool": tool_name,
        "success": result.success and not result.needs_approval,
        "response": resp,
        "needs_approval": result.needs_approval,
    }


def check_globex_agent_health() -> dict[str, Any]:
    settings = get_settings()
    tags_ok = False
    inference_ok = False
    detail: str | None = None
    try:
        import httpx

        base = settings.ollama_base_url.rstrip("/")
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/api/tags")
            tags_ok = resp.status_code == 200
            if not tags_ok:
                detail = f"tags HTTP {resp.status_code}"
    except Exception as exc:
        detail = str(exc)

    if tags_ok:
        inference_ok = ollama_inference_ready()
        if not inference_ok:
            detail = (
                f"Ollama répond sur /api/tags mais l'inférence échoue "
                f"(modèle {settings.ollama_model})"
            )

    kernel_ver = "simple-v0" if settings.globex_simple_mode else "client-arch-v1"
    return {
        "enabled": settings.globex_agent_enabled,
        "ollama_model": settings.ollama_model,
        "ollama_online": tags_ok,
        "ollama_tags_ok": tags_ok,
        "ollama_inference_ok": inference_ok if tags_ok else False,
        "detail": detail,
        "kernel_version": kernel_ver,
        "simple_mode": settings.globex_simple_mode,
    }


def list_globex_agent_tools(db: Session, admin: User, *, agent_mode: bool = True) -> list[dict[str, Any]]:
    gpt = load_gpt_by_slug(db, SLUG_ADMIN)
    if gpt is None:
        return []
    role = (admin.role or "admin").lower()
    tools = filter_tools_for_admin_mode(
        list_tools_for_gpt(gpt, user_role=role),
        analysis_mode=not agent_mode,
    )
    return [
        {
            "name": t.name,
            "description": t.description[:200],
            "sensitivity": t.sensitivity,
            "requires_approval": t.requires_approval,
        }
        for t in tools
    ]
