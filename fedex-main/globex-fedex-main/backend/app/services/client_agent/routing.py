# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Routage minimal client — FedEx vs Ollama."""
#
# from __future__ import annotations
#
# import re
#
# from app.services.chat_export_service import is_export_intent
# from app.services.chat_session_context import message_unrelated_to_shipment
# from app.services.client_agent.export_routing import is_pdf_export_intent
# from app.services.llm.providers import normalize_lang_code
# from app.services.llm.tracking_extract import extract_tracking_number
#
# _AGENT_ACTION_INTENT = re.compile(
#     r"(surveill|watch\s+(?:this\s+)?(?:package|shipment|colis)|"
#     r"alerte.{0,30}colis|"
#     r"ouvrir\s+un\s+ticket|open\s+(?:a\s+)?support\s+ticket|ticket\s+support)",
#     re.I,
# )
#
#
# def is_agent_action_intent(message: str) -> bool:
#     """Surveillance colis, tickets support — nécessitent la boucle outils."""
#     return bool(_AGENT_ACTION_INTENT.search(message or ""))
#
#
# def should_use_fedex_path(message: str, tracking: str | None) -> bool:
#     """True si un numéro de suivi est résolu et le message concerne le colis."""
#     if not (tracking or "").strip():
#         return False
#     if extract_tracking_number(message):
#         return True
#     if message_unrelated_to_shipment(message):
#         return False
#     return True
#
#
# def is_shipment_question_without_tracking(message: str, tracking: str | None) -> bool:
#     """Question colis sans numéro résolu (session ou message)."""
#     if (tracking or "").strip():
#         return False
#     return not message_unrelated_to_shipment(message)
#
#
# def should_use_conversational_light_path(message: str, tracking: str | None) -> bool:
#     """True pour bonjour, merci, FAQ générale — chemin Ollama léger sans outils."""
#     if is_pdf_export_intent(message) or is_export_intent(message):
#         return False
#     if is_agent_action_intent(message):
#         return False
#     if should_use_fedex_path(message, tracking):
#         return False
#     if is_shipment_question_without_tracking(message, tracking):
#         return False
#     return message_unrelated_to_shipment(message)
#
#
# def missing_tracking_prompt(ui_language: str | None = None) -> str:
#     lang = normalize_lang_code(ui_language)
#     if lang == "en":
#         return (
#             "To track your shipment, please share your **FedEx tracking number** "
#             "(12 to 14 digits)."
#         )
#     if lang == "ar":
#         return "لمتابعة شحنتك، يرجى إرسال **رقم التتبع FedEx** (12 إلى 14 رقمًا)."
#     return (
#         "Pour suivre votre colis, merci de me communiquer votre **numéro de suivi FedEx** "
#         "(12 à 14 chiffres)."
#     )
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
