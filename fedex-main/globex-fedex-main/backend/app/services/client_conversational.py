# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Messages conversationnels client (salutations, capacités) sans hallucination colis."""
#
# from __future__ import annotations
#
# import re
#
# from app.services.llm.providers import normalize_lang_code
#
# _GREETING_RE = re.compile(
#     r"^(bonjour|salut|coucou|bonsoir|hello|hi|hey|good\s+evening|merci|thanks|thank you|"
#     r"au revoir|bye|à bientôt|a bientot)[\s!.?]*$",
#     re.I,
# )
#
# _CAPABILITIES_RE = re.compile(
#     r"\b(que\s+(peux|peut|sais|savez)[-\s]?tu\s+faire|"
#     r"qu'?est[- ]ce que tu fais|tes\s+capacit|what can you do|comment\s+tu\s+peux\s+m'aider)\b",
#     re.I,
# )
#
#
# def is_client_conversational_message(message: str) -> bool:
#     """Salutation, remerciement ou question sur les capacités de l'assistant."""
#     text = (message or "").strip()
#     if not text:
#         return False
#     if _GREETING_RE.match(text):
#         return True
#     return bool(_CAPABILITIES_RE.search(text))
#
#
# def is_client_greeting_only(message: str) -> bool:
#     return bool(_GREETING_RE.match((message or "").strip()))
#
#
# def is_client_capabilities_message(message: str) -> bool:
#     return bool(_CAPABILITIES_RE.search((message or "").strip()))
#
#
# def client_greeting_reply(
#     *,
#     ui_language: str | None = None,
#     preferred_name: str | None = None,
#     message: str = "",
# ) -> str:
#     """Réponse locale pour salutations client (sans LLM)."""
#     lang = normalize_lang_code(ui_language)
#     name = (preferred_name or "").strip()
#     low = (message or "").lower().strip()
#
#     if lang == "en":
#         if re.match(r"^(thanks|merci)", low):
#             return "You're welcome! How can I help with your FedEx shipment today?"
#         if re.match(r"^(bye|au revoir)", low):
#             return "Goodbye! Feel free to come back if you need tracking help."
#         greeting = f"Hello {name}" if name else "Hello"
#         return (
#             f"{greeting}! I'm your **FedEx assistant**.\n\n"
#             "I can track packages, show scan history, delivery estimates, and answer "
#             "general FedEx logistics questions. Share a tracking number (12–14 digits) "
#             "or tell me what you need."
#         )
#
#     if lang == "ar":
#         greeting = f"مرحباً {name}" if name else "مرحباً"
#         return (
#             f"{greeting}! أنا **مساعد FedEx** الخاص بك.\n\n"
#             "يمكنني تتبع الطرود وعرض سجل المسح وتقديرات التسليم. "
#             "أرسل رقم تتبع (12–14 رقماً) أو اطرح سؤالك."
#         )
#
#     if re.match(r"^(merci|thanks)", low):
#         return "Avec plaisir ! Que puis-je faire d'autre pour vous concernant vos envois FedEx ?"
#     if re.match(r"^(au revoir|bye)", low):
#         return "Au revoir ! Revenez quand vous voulez pour le suivi de vos colis."
#     if re.match(r"^bonsoir", low):
#         salutation = f"Bonsoir {name}" if name else "Bonsoir"
#     elif re.match(r"^(salut|coucou)", low):
#         salutation = f"Salut {name}" if name else "Salut"
#     else:
#         salutation = f"Bonjour {name}" if name else "Bonjour"
#
#     return (
#         f"{salutation} ! Je suis votre **assistant FedEx**.\n\n"
#         "Je peux suivre vos colis, afficher l'historique des scans, les délais de livraison "
#         "et répondre à vos questions sur les services FedEx. "
#         "Indiquez un numéro de suivi (12 à 14 chiffres) ou dites-moi ce dont vous avez besoin."
#     )
#
#
# def client_capabilities_reply(*, ui_language: str | None = None, preferred_name: str | None = None) -> str:
#     lang = normalize_lang_code(ui_language)
#     name = (preferred_name or "").strip()
#     if lang == "en":
#         hi = f"Hello {name}! " if name else ""
#         return (
#             f"{hi}I'm your FedEx assistant. I can:\n"
#             "- Track packages with a FedEx number\n"
#             "- Show scan history and delivery status\n"
#             "- Answer general questions about FedEx services and delivery times\n\n"
#             "Send a tracking number or ask your question."
#         )
#     greeting = f"Bonjour {name} ! " if name else ""
#     return (
#         f"{greeting}Je suis votre assistant FedEx. Je peux :\n"
#         "- Suivre un colis avec un numéro FedEx\n"
#         "- Afficher l'historique des scans et le statut de livraison\n"
#         "- Répondre aux questions générales sur les services et délais FedEx\n\n"
#         "Envoyez un numéro de suivi ou posez votre question."
#     )
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Messages conversationnels client — stub Phase 0."""
