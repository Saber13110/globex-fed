"""
Orchestration LLM : Gemini Flash par défaut, Ollama gemma3 en secours.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.llm import fedex_context, intent_detection, tracking_extract
from app.services.llm.fedex_context import format_fedex_context_for_prompt
from app.services.llm.providers import (
    LlmProviderError,
    call_gemini,
    call_gemini_title,
    call_ollama,
    normalize_lang_code,
)
from app.services.llm.session_title import (
    heuristic_session_title,
    is_acceptable_title,
    sanitize_session_title,
)

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"
PROVIDER_OLLAMA = "ollama"

INTENT_TRACK = "track_package"
INTENT_GENERAL = "general_question"


@dataclass
class LlmChatResult:
    reply: str
    intent: str
    tracking_number: str | None
    llm_provider: str
    fedex_data_available: bool = False


def _anti_hallucination_track_reply(
    tracking_number: str,
    fedex_payload: dict,
    ui_language: str | None,
) -> str:
    """Réponse déterministe si FedEx indisponible — jamais de faux statut."""
    lang = normalize_lang_code(ui_language)
    msg = fedex_payload.get("message", "Données FedEx indisponibles.")
    if lang == "en":
        return (
            f"I detected tracking number **{tracking_number}**, but I cannot confirm the real "
            f"package status without a response from the FedEx API.\n\n{msg}"
        )
    if lang == "ar":
        return (
            f"تم التعرف على رقم التتبع **{tracking_number}**، لكن لا يمكنني تأكيد الحالة الفعلية "
            f"للطرد دون استجابة من واجهة FedEx.\n\n{msg}"
        )
    return (
        f"J'ai détecté le numéro de suivi **{tracking_number}**, mais je ne peux pas confirmer "
        f"le statut réel du colis sans réponse de l'API FedEx.\n\n{msg}"
    )


def _format_fedex_deterministic_reply(data: dict) -> str:
    """Réponse factuelle basée uniquement sur les champs FedEx réels."""
    return (
        f"Voici le suivi pour le colis **{data['tracking_number']}** (données FedEx réelles).\n"
        f"- Statut : {data.get('status') or 'non communiqué'}\n"
        f"- Localisation : {data.get('current_location') or 'non communiquée'}\n"
        f"- Livraison estimée : {data.get('estimated_delivery') or 'non communiquée'}"
    )


def _default_message_for_image(ui_language: str | None) -> str:
    lang = normalize_lang_code(ui_language)
    if lang == "en":
        return "What can you tell me about this FedEx image?"
    if lang == "ar":
        return "ماذا يمكنك أن تخبرني عن هذه الصورة المتعلقة بـ FedEx؟"
    return "Que peux-tu me dire à propos de cette image FedEx ?"


def generate_response(
    user_message: str,
    *,
    response_preferences: str | None = None,
    preferred_name: str | None = None,
    ui_language: str | None = None,
    fedex_context_json: str | None = None,
    force_intent: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    skip_fedex_fetch: bool = False,
    conversation_history: str | None = None,
) -> LlmChatResult:
    """
    Génère une réponse avec détection d'intention, anti-hallucination suivi,
    Gemini puis fallback Ollama.
    """
    settings = get_settings()
    effective_message = (user_message or "").strip()
    if not effective_message and image_base64:
        effective_message = _default_message_for_image(ui_language)
    tracking_number = tracking_extract.extract_tracking_number(effective_message)
    intent = force_intent or intent_detection.detect_intent(effective_message, tracking_number)

    if tracking_number:
        from app.utils.tracking_parser import is_plausible_tracking_number

        if not is_plausible_tracking_number(tracking_number):
            tracking_number = None
            if intent == INTENT_TRACK and not force_intent:
                intent = INTENT_GENERAL

    fedex_payload: dict | None = None
    fedex_ctx_str = fedex_context_json
    fedex_data_available = False

    if skip_fedex_fetch and fedex_context_json:
        try:
            import json as _json

            fedex_payload = _json.loads(fedex_context_json)
            fedex_data_available = bool(fedex_payload.get("available"))
        except Exception:
            fedex_payload = {"available": False}
    elif intent == INTENT_TRACK and tracking_number:
        fedex_payload = fedex_context.fetch_fedex_tracking_data(tracking_number)
        if not fedex_ctx_str:
            fedex_ctx_str = format_fedex_context_for_prompt(fedex_payload)
        fedex_data_available = bool(fedex_payload.get("available"))

        if not skip_fedex_fetch and not fedex_payload.get("available"):
            return LlmChatResult(
                reply=_anti_hallucination_track_reply(tracking_number, fedex_payload, ui_language),
                intent=intent,
                tracking_number=tracking_number,
                llm_provider="none",
                fedex_data_available=False,
            )

        if (
            not skip_fedex_fetch
            and settings.use_deterministic_fedex_reply
            and fedex_payload.get("available")
        ):
            raw = fedex_payload.get("shipment") or fedex_payload.get("raw") or fedex_payload
            return LlmChatResult(
                reply=_format_fedex_deterministic_reply(raw if isinstance(raw, dict) else fedex_payload),
                intent=intent,
                tracking_number=tracking_number,
                llm_provider="fedex_api",
                fedex_data_available=True,
            )

    provider_used = PROVIDER_GEMINI
    try:
        if settings.llm_primary_provider.lower() == PROVIDER_GEMINI:
            reply = _try_gemini_then_ollama(
                effective_message,
                fedex_context=fedex_ctx_str,
                conversation_history=conversation_history,
                response_preferences=response_preferences,
                preferred_name=preferred_name,
                ui_language=ui_language,
                intent=intent,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
            )
            provider_used = reply[1]
            text = reply[0]
        else:
            if image_base64:
                raise LlmProviderError(
                    "L'analyse d'image nécessite Gemini. Ollama seul ne prend pas en charge les images."
                )
            text = call_ollama(
                effective_message,
                fedex_context=fedex_ctx_str,
                conversation_history=conversation_history,
                response_preferences=response_preferences,
                preferred_name=preferred_name,
                ui_language=ui_language,
                intent=intent,
            )
            provider_used = PROVIDER_OLLAMA
    except LlmProviderError as exc:
        logger.error("Tous les fournisseurs LLM ont échoué : %s", exc)
        raise

    return LlmChatResult(
        reply=text,
        intent=intent,
        tracking_number=tracking_number,
        llm_provider=provider_used,
        fedex_data_available=bool(
            fedex_data_available or (fedex_payload and fedex_payload.get("available"))
        ),
    )


def _try_gemini_then_ollama(
    user_message: str,
    *,
    fedex_context: str | None,
    conversation_history: str | None = None,
    response_preferences: str | None,
    preferred_name: str | None,
    ui_language: str | None,
    intent: str,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    try:
        text = call_gemini(
            user_message,
            fedex_context=fedex_context,
            conversation_history=conversation_history,
            response_preferences=response_preferences,
            preferred_name=preferred_name,
            ui_language=ui_language,
            intent=intent,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
        return text, PROVIDER_GEMINI
    except LlmProviderError as gemini_err:
        if image_base64:
            raise LlmProviderError(
                "Impossible d'analyser l'image (Gemini indisponible). Réessayez plus tard."
            ) from gemini_err
        logger.warning(
            "Tous les modèles Gemini ont échoué, bascule Ollama (%s) — réponse plus lente : %s",
            settings.ollama_model,
            gemini_err,
        )
        text = call_ollama(
            user_message,
            fedex_context=fedex_context,
            conversation_history=conversation_history,
            response_preferences=response_preferences,
            preferred_name=preferred_name,
            ui_language=ui_language,
            intent=intent,
        )
        return text, PROVIDER_OLLAMA


def generate_support_reply(
    user_message: str,
    response_preferences: str | None = None,
    preferred_name: str | None = None,
    ui_language: str | None = None,
) -> str:
    """Compatibilité chatbot_service — retourne uniquement le texte."""
    result = generate_response(
        user_message,
        response_preferences=response_preferences,
        preferred_name=preferred_name,
        ui_language=ui_language,
    )
    return result.reply


def generate_session_title(
    user_message: str,
    *,
    bot_reply: str | None = None,
    ui_language: str | None = None,
    intent: str | None = None,
    tracking_number: str | None = None,
    has_image: bool = False,
) -> str:
    """Titre style ChatGPT : court, basé sur le 1er message utilisateur (Gemini puis heuristique)."""
    settings = get_settings()
    if settings.llm_primary_provider.lower() == PROVIDER_GEMINI and (settings.gemini_api_key or "").strip():
        try:
            title = call_gemini_title(
                user_message,
                bot_reply=bot_reply,
                ui_language=ui_language,
            )
            cleaned = sanitize_session_title(title)
            if cleaned and is_acceptable_title(cleaned):
                return cleaned
            return heuristic_session_title(
                user_message,
                ui_language=ui_language,
                intent=intent,
                tracking_number=tracking_number,
                has_image=has_image,
            )
        except LlmProviderError as exc:
            logger.info("Titre Gemini indisponible, titre local : %s", exc)

    return heuristic_session_title(
        user_message,
        ui_language=ui_language,
        intent=intent,
        tracking_number=tracking_number,
        has_image=has_image,
    )
