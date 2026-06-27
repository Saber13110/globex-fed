# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Pont Ollama Phase 1 — /api/chat, style ollama run."""
#
# from __future__ import annotations
#
# import logging
# from typing import Any
#
# import httpx
#
# from app.core.config import get_settings
# from app.services.llm.providers import _extract_ollama_text, normalize_lang_code
#
# logger = logging.getLogger(__name__)
#
# _IMAGE_NOTE_FR = (
#     "\n\n[Note : l'utilisateur a joint une image — ce modèle ne la voit pas ; "
#     "aidez-le avec le texte fourni.]"
# )
# _IMAGE_NOTE_EN = (
#     "\n\n[Note: the user attached an image — this model cannot see it; "
#     "help based on the text provided.]"
# )
#
# _FALLBACK_LLM_DISABLED_FR = (
#     "Le service de langage est désactivé (LLM_ENABLED=false). "
#     "Activez-le dans la configuration pour obtenir des réponses Ollama."
# )
# _FALLBACK_LLM_DISABLED_EN = (
#     "The language service is disabled (LLM_ENABLED=false). "
#     "Enable it in configuration to get Ollama responses."
# )
# _FALLBACK_OLLAMA_FR = (
#     "Ollama ne répond pas pour le moment (connexion ou délai dépassé). "
#     "Vérifiez qu'Ollama est lancé (`ollama serve`) et que le modèle est installé."
# )
# _FALLBACK_OLLAMA_EN = (
#     "Ollama is not responding (connection or timeout). "
#     "Check that Ollama is running (`ollama serve`) and the model is installed."
# )
# _FALLBACK_EMPTY_FR = "Ollama a renvoyé une réponse vide. Réessayez dans un instant."
# _FALLBACK_EMPTY_EN = "Ollama returned an empty response. Please try again shortly."
#
#
# def _system_prompt(ui_language: str | None) -> str:
#     lang = normalize_lang_code(ui_language)
#     if lang == "en":
#         return (
#             "You are a helpful conversational assistant. "
#             "Reply in English. You can discuss FedEx and logistics. "
#             "If you do not know something, say so honestly."
#         )
#     if lang == "ar":
#         return (
#             "أنت مساعد محادثة مفيد. أجب بالعربية. يمكنك المساعدة في FedEx واللوجستيات. "
#             "إذا لم تكن تعرف شيئاً، قل ذلك بصدق."
#         )
#     return (
#         "Tu es un assistant conversationnel utile. Réponds en français. "
#         "Tu peux aider sur FedEx et la logistique. "
#         "Si tu ne sais pas quelque chose, dis-le honnêtement."
#     )
#
#
# def _append_user_content(
#     user_message: str,
#     *,
#     ui_language: str | None,
#     has_image: bool,
# ) -> str:
#     text = (user_message or "").strip() or "(message vide)"
#     if has_image:
#         note = _IMAGE_NOTE_EN if normalize_lang_code(ui_language) == "en" else _IMAGE_NOTE_FR
#         text = f"{text}{note}"
#     return text
#
#
# def chat_turn(
#     *,
#     user_message: str,
#     history_messages: list[dict[str, str]],
#     ui_language: str | None = None,
#     has_image: bool = False,
#     system_instruction: str | None = None,
# ) -> tuple[str, str]:
#     """
#     Envoie un tour à Ollama via /api/chat.
#
#     Retourne (reply, source) avec source « ollama » ou « fallback ».
#     Ne lève jamais d'exception vers l'appelant.
#     """
#     settings = get_settings()
#     lang = normalize_lang_code(ui_language)
#
#     if not settings.llm_enabled:
#         msg = _FALLBACK_LLM_DISABLED_EN if lang == "en" else _FALLBACK_LLM_DISABLED_FR
#         return msg, "fallback"
#
#     base = settings.ollama_base_url.rstrip("/")
#     model = settings.ollama_model
#     user_content = _append_user_content(user_message, ui_language=ui_language, has_image=has_image)
#
#     system = (system_instruction or "").strip() or _system_prompt(ui_language)
#     messages: list[dict[str, str]] = [{"role": "system", "content": system}]
#     for item in history_messages:
#         role = str(item.get("role") or "").strip()
#         content = str(item.get("content") or "").strip()
#         if role in ("user", "assistant") and content:
#             messages.append({"role": role, "content": content})
#     messages.append({"role": "user", "content": user_content})
#
#     body: dict[str, Any] = {
#         "model": model,
#         "messages": messages,
#         "stream": False,
#         "think": False,
#         "options": {
#             "temperature": 0.7,
#             "num_predict": 1024,
#             "num_ctx": 8192,
#         },
#     }
#
#     timeout = httpx.Timeout(
#         connect=10.0,
#         read=max(settings.ollama_timeout_seconds, 60.0),
#         write=30.0,
#         pool=5.0,
#     )
#
#     try:
#         with httpx.Client(timeout=timeout) as client:
#             resp = client.post(f"{base}/api/chat", json=body)
#             resp.raise_for_status()
#             data = resp.json()
#     except httpx.TimeoutException:
#         logger.warning("client_agent ollama_bridge timeout model=%s", model)
#         msg = _FALLBACK_OLLAMA_EN if lang == "en" else _FALLBACK_OLLAMA_FR
#         return msg, "fallback"
#     except Exception:
#         logger.exception("client_agent ollama_bridge request failed model=%s", model)
#         msg = _FALLBACK_OLLAMA_EN if lang == "en" else _FALLBACK_OLLAMA_FR
#         return msg, "fallback"
#
#     reply = _extract_ollama_text(data)
#     if not reply:
#         msg = _FALLBACK_EMPTY_EN if lang == "en" else _FALLBACK_EMPTY_FR
#         return msg, "fallback"
#
#     return reply, "ollama"
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
