# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Composition de texte PDF via Ollama — résumé conversation client."""
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
# _MAX_BODY = 3000
#
#
# def _pdf_compose_system(ui_language: str | None) -> str:
#     lang = normalize_lang_code(ui_language)
#     if lang == "en":
#         return (
#             "You write plain-text document bodies for PDF export. "
#             "Use a short title line, then structured sections. "
#             "Base content ONLY on the conversation provided. "
#             "Do NOT invent package tracking statuses or delivery facts. "
#             "If shipment data is missing, say so. Reply in English. No markdown."
#         )
#     if lang == "ar":
#         return (
#             "أنت تكتب نصوص مستندات PDF. استخدم عنواناً قصيراً ثم أقساماً. "
#             "اعتمد فقط على المحادثة المقدمة. لا تخترع حالات شحن أو توصيل. "
#             "أجب بالعربية. بدون markdown."
#         )
#     return (
#         "Tu rédiges le corps d'un document PDF en texte brut. "
#         "Commence par un titre court, puis des sections structurées. "
#         "Base-toi UNIQUEMENT sur la conversation fournie. "
#         "N'invente JAMAIS de statuts colis ou de faits de livraison. "
#         "Si des données colis manquent, dis-le. Réponds en français. Pas de markdown."
#     )
#
#
# def compose_pdf_text_with_ollama(
#     *,
#     user_request: str,
#     conversation_text: str,
#     ui_language: str | None = None,
# ) -> tuple[str, str]:
#     """
#     Demande à Ollama de rédiger le contenu du PDF.
#
#     Retourne (text, source) — source « ollama » ou « fallback ».
#     """
#     settings = get_settings()
#     lang = normalize_lang_code(ui_language)
#
#     conv = (conversation_text or "").strip()[:8000]
#     if not conv:
#         if lang == "en":
#             return "Empty conversation — nothing to export.", "fallback"
#         if lang == "ar":
#             return "محادثة فارغة — لا يوجد محتوى للتصدير.", "fallback"
#         return "Conversation vide — rien à exporter.", "fallback"
#
#     if not settings.llm_enabled:
#         return conv[:_MAX_BODY], "fallback"
#
#     base = settings.ollama_base_url.rstrip("/")
#     model = settings.ollama_model
#     user_content = (
#         f"Demande utilisateur : {user_request.strip()}\n\n"
#         f"--- Conversation ---\n{conv}\n\n"
#         "Rédige le contenu du PDF (texte brut, max ~2500 mots)."
#     )
#
#     body: dict[str, Any] = {
#         "model": model,
#         "messages": [
#             {"role": "system", "content": _pdf_compose_system(ui_language)},
#             {"role": "user", "content": user_content},
#         ],
#         "stream": False,
#         "think": False,
#         "options": {
#             "temperature": 0.4,
#             "num_predict": 1536,
#             "num_ctx": 8192,
#         },
#     }
#
#     timeout = httpx.Timeout(connect=10.0, read=max(settings.ollama_timeout_seconds, 90.0), write=30.0, pool=5.0)
#
#     try:
#         with httpx.Client(timeout=timeout) as client:
#             resp = client.post(f"{base}/api/chat", json=body)
#             resp.raise_for_status()
#             data = resp.json()
#     except Exception:
#         logger.exception("compose_pdf_text_with_ollama failed")
#         return conv[:_MAX_BODY], "fallback"
#
#     reply = _extract_ollama_text(data)
#     if not reply:
#         return conv[:_MAX_BODY], "fallback"
#     return reply.strip()[:_MAX_BODY], "ollama"
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
