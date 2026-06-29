"""Chat Ollama admin — pattern client (léger, sans outils)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm.providers import LlmProviderError, _extract_ollama_text, normalize_lang_code
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)

_ADMIN_CHAT_TIMEOUT_SECONDS = 60.0
_SIMPLE_NUM_PREDICT = 128
_SIMPLE_NUM_CTX = 512


def _admin_system_prompt(*, lang: str, agent_mode: bool) -> str:
    mode = (
        "Mode AGENT — tu peux proposer des actions concrètes sur la plateforme."
        if agent_mode
        else "Mode ANALYSE — consultation et conseils, pas d'actions destructives."
    )
    if lang == "en":
        return (
            "You are **Jarvis**, Globex FedEx Super Admin assistant.\n"
            "You help with tracking, users, tickets, logs, KPIs and exports.\n"
            "Answer naturally and concisely (2-6 sentences). "
            "Do not invent data — suggest what you can do if asked.\n"
            f"{mode}\n"
            f"{language_lock_instruction(lang)}"
        )
    if lang == "ar":
        return (
            "أنت **Jarvis**، مساعد Globex FedEx للمشرف.\n"
            "ساعد في التتبع والمستخدمين والتذاكر والسجلات ومؤشرات الأداء.\n"
            f"{mode}\n"
            f"{language_lock_instruction(lang)}"
        )
    return (
        "Tu es **Jarvis**, agent Super Admin Globex FedEx.\n"
        "Tu aides sur colis, utilisateurs, tickets, journaux, KPI et exports.\n"
        "Réponds naturellement et brièvement (2-6 phrases). "
        "N'invente pas de chiffres — si on te demande ce que tu sais faire, liste tes domaines.\n"
        f"{mode}\n"
        f"{language_lock_instruction(lang)}"
    )


def _admin_simple_system_prompt(*, lang: str) -> str:
    if lang == "en":
        return (
            "You are Jarvis, Globex FedEx admin assistant. "
            "Reply briefly and warmly. If asked what you can do, mention shipments, users, tickets, logs and exports.\n"
            f"{language_lock_instruction(lang)}"
        )
    if lang == "ar":
        return (
            "أنت Jarvis، مساعد Globex FedEx. أجب باختصار وبلطف. "
            "إذا سُئلت عما يمكنك فعله، اذكر الشحنات والمستخدمين والتذاكر والسجلات.\n"
            f"{language_lock_instruction(lang)}"
        )
    return (
        "Tu es Jarvis, assistant admin Globex FedEx.\n"
        "Réponds brièvement et chaleureusement. Si on te demande ce que tu sais faire, "
        "liste colis, utilisateurs, tickets, journaux et exports.\n"
        f"{language_lock_instruction(lang)}"
    )


def _history_to_messages(
    conversation_history: list[dict[str, str]] | None,
    *,
    max_turns: int = 8,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in (conversation_history or [])[-max_turns:]:
        role_raw = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role_raw in ("user", "admin"):
            role = "user"
        elif role_raw in ("assistant", "jarvis", "bot"):
            role = "assistant"
        else:
            continue
        out.append({"role": role, "content": content[:800]})
    return out


def _admin_ollama_chat_simple(
    message: str,
    *,
    ui_language: str = "fr",
) -> str:
    """Phase 0 — /api/generate minimal (comme ollama run en terminal)."""
    settings = get_settings()
    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé (LLM_ENABLED=false).")

    lang = normalize_lang_code(ui_language)
    msg = (message or "").strip() or "Bonjour"
    system = _admin_simple_system_prompt(lang=lang)
    prompt = f"===SYSTEM===\n{system}\n\n===USER===\n{msg}"

    base = settings.ollama_base_url.rstrip("/")
    body: dict[str, Any] = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": _SIMPLE_NUM_PREDICT,
            "num_ctx": _SIMPLE_NUM_CTX,
        },
    }
    read_timeout = min(float(settings.ollama_timeout_seconds or 90), 90.0)
    timeout = httpx.Timeout(connect=5.0, read=read_timeout, write=15.0, pool=5.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as exc:
        raise LlmProviderError(f"Timeout Ollama simple admin ({settings.ollama_model})") from exc
    except Exception as exc:
        raise LlmProviderError(f"Échec Ollama simple admin : {exc}") from exc

    reply = str(data.get("response") or "").strip() or _extract_ollama_text(data)
    if not reply:
        raise LlmProviderError("Réponse Ollama vide.")
    logger.info("[GlobexAgent] admin_ollama_chat_simple OK — %s chars", len(reply))
    return reply


def admin_ollama_chat(
    message: str,
    *,
    ui_language: str = "fr",
    conversation_history: list[dict[str, str]] | None = None,
    agent_mode: bool = True,
) -> str:
    """
    Chat conversationnel admin via Ollama (sans outils).
    Phase 0 (GLOBEX_SIMPLE_MODE) : /api/generate minimal sans historique.
    Phase 1+ : /api/chat avec historique.
    """
    settings = get_settings()
    if settings.globex_simple_mode:
        return _admin_ollama_chat_simple(message, ui_language=ui_language)

    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé (LLM_ENABLED=false).")

    lang = normalize_lang_code(ui_language)
    user_content = (message or "").strip() or "Bonjour"
    system = _admin_system_prompt(lang=lang, agent_mode=agent_mode)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(_history_to_messages(conversation_history))
    messages.append({"role": "user", "content": user_content})

    base = settings.ollama_base_url.rstrip("/")
    body: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.35,
            "num_predict": 256,
            "num_ctx": 2048,
        },
    }
    timeout = httpx.Timeout(
        connect=8.0,
        read=min(float(settings.ollama_timeout_seconds or 120), _ADMIN_CHAT_TIMEOUT_SECONDS),
        write=20.0,
        pool=5.0,
    )

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as exc:
        raise LlmProviderError(f"Timeout Ollama chat admin ({settings.ollama_model})") from exc
    except Exception as exc:
        raise LlmProviderError(f"Échec Ollama chat admin : {exc}") from exc

    msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    reply = str(msg.get("content") or "").strip() or _extract_ollama_text(data)
    if not reply:
        raise LlmProviderError("Réponse Ollama vide.")
    logger.info("[GlobexAgent] admin_ollama_chat OK — %s chars", len(reply))
    return reply
