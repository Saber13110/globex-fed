"""Passerelle modèle — toute réponse Gemini passe par un contexte assemblé."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.gpt.rag_profiler import RagProfile
from app.services.llm.providers import (
    LlmProviderError,
    _gemini_generate,
    normalize_lang_code,
    should_skip_gemini,
)
from app.services.llm.gemini_budget import note_fallback
from app.services.gpt.prompts import admin_gpt_system_for_lang, client_gpt_system_for_lang

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"
PROVIDER_OLLAMA = "ollama"


@dataclass
class GptModelResult:
    reply: str
    llm_provider: str


def resolve_system_prompt(*, gpt_slug: str, ui_language: str | None) -> str:
    lang = normalize_lang_code(ui_language)
    if gpt_slug.startswith("fedex-admin"):
        return admin_gpt_system_for_lang(lang)
    return client_gpt_system_for_lang(lang)


def generate_with_context(
    *,
    gpt_slug: str,
    user_payload: str,
    ui_language: str | None = "fr",
    max_output_tokens: int = 1024,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    profile: RagProfile | None = None,
) -> GptModelResult:
    """Appelle Gemini (puis Ollama) avec system prompt GPT + payload contextualisé."""
    settings = get_settings()
    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé (LLM_ENABLED=false).")

    if not (user_payload or "").strip():
        raise LlmProviderError("Payload vide — le modèle ne doit jamais être appelé sans contexte.")

    lang = normalize_lang_code(ui_language)
    system = resolve_system_prompt(gpt_slug=gpt_slug, ui_language=lang)
    payload = user_payload
    max_chars = max(settings.llm_max_prompt_chars, 1500)
    if len(payload) > max_chars:
        payload = payload[:max_chars] + "\n… [payload tronqué pour le modèle]"
        logger.warning("Payload GPT tronqué à %s caractères (slug=%s)", max_chars, gpt_slug)

    if settings.llm_primary_provider.strip().lower() == "gemini" and not should_skip_gemini():
        try:
            t0 = time.perf_counter()
            text = _gemini_generate(
                payload,
                max_output_tokens=max_output_tokens,
                system_instruction=system,
                ui_language=lang,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
            )
            if profile:
                profile.add("gemini_generate", detail=f"ms={int((time.perf_counter()-t0)*1000)}")
            return GptModelResult(reply=text, llm_provider=PROVIDER_GEMINI)
        except LlmProviderError as exc:
            logger.warning("Gemini GPT runtime échoué, secours Ollama : %s", exc)
    elif should_skip_gemini():
        logger.info("Gemini ignoré (429/budget/cooldown global) — passage direct Ollama")

    note_fallback(PROVIDER_OLLAMA)
    ollama_payload = payload
    ollama_cap = min(max_chars, 1500)
    if len(ollama_payload) > ollama_cap:
        ollama_payload = ollama_payload[:ollama_cap] + "\n… [troncature Ollama]"
    if gpt_slug.startswith("fedex-admin"):
        ollama_system = (
            "Tu es Fedex-v0, assistant FedEx pour administrateur. Réponds en français, "
            "concis, chaleureux et professionnel — comme un collègue humain. "
            "Ne cite jamais de noms d'outils techniques ni de JSON."
        )
    else:
        ollama_system = system[:1200] + ("…" if len(system) > 1200 else "")
    ollama_prompt = f"===SYSTEM===\n{ollama_system}\n\n===USER_PAYLOAD===\n{ollama_payload}"
    try:
        import httpx

        settings = get_settings()

        base = settings.ollama_base_url.rstrip("/")
        body = {
            "model": settings.ollama_model,
            "prompt": ollama_prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": min(max_output_tokens, 320),
                "num_ctx": 4096,
            },
        }
        read_timeout = max(float(settings.ollama_timeout_seconds), 180.0)
        timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=5.0)
        t0 = time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
        if profile:
            profile.add(
                "ollama_generate",
                detail=f"ms={int((time.perf_counter()-t0)*1000)} model={settings.ollama_model}",
            )
        reply = (data.get("response") or "").strip()
        if not reply and isinstance(data.get("message"), dict):
            reply = (data["message"].get("content") or "").strip()
        if not reply:
            raise LlmProviderError("Réponse Ollama vide.")
        return GptModelResult(reply=reply, llm_provider=PROVIDER_OLLAMA)
    except Exception as exc:
        raise LlmProviderError(f"Tous les fournisseurs LLM ont échoué : {exc}") from exc


def generate_ollama_admin_fast(
    task: str,
    *,
    context: str = "",
    conversation_history: str = "",
    ui_language: str | None = "fr",
    max_output_tokens: int = 200,
) -> GptModelResult:
    """Appel Ollama minimal pour le repli Copilot admin (sans RAG ni prompt lourd)."""
    settings = get_settings()
    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé.")

    task_clean = (task or "").strip()
    if not task_clean:
        raise LlmProviderError("Question vide.")

    lang = normalize_lang_code(ui_language)
    lang_label = {"fr": "français", "en": "anglais", "ar": "arabe"}.get(lang, "français")
    parts: list[str] = []
    ctx = (context or "").strip()
    if ctx:
        parts.append(f"Contexte plateforme (extrait):\n{ctx[:500]}")
    hist = (conversation_history or "").strip()
    if hist:
        parts.append(f"Historique:\n{hist[-600:]}")
    parts.append(f"Question administrateur:\n{task_clean[:1200]}")
    user_block = "\n\n".join(parts)

    note_fallback(PROVIDER_OLLAMA)
    import httpx

    body = {
        "model": settings.ollama_model,
        "prompt": (
            f"Tu es Fedex-v0 (admin Globex FedEx). Réponds en {lang_label}, "
            f"naturellement (2-6 phrases), sans jargon technique.\n\n"
            f"{user_block}"
        ),
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": min(max(max_output_tokens, 64), 220),
            "num_ctx": 2048,
        },
    }
    read_timeout = min(max(float(settings.ollama_timeout_seconds), 60.0), 120.0)
    timeout = httpx.Timeout(connect=8.0, read=read_timeout, write=20.0, pool=5.0)
    base = settings.ollama_base_url.rstrip("/")
    try:
        t0 = time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
        reply = (data.get("response") or "").strip()
        if not reply:
            raise LlmProviderError("Réponse Ollama vide.")
        logger.info(
            "Ollama admin fast OK — model=%s ms=%s",
            settings.ollama_model,
            int((time.perf_counter() - t0) * 1000),
        )
        return GptModelResult(reply=reply, llm_provider=PROVIDER_OLLAMA)
    except Exception as exc:
        raise LlmProviderError(f"Ollama indisponible : {exc}") from exc
