# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Correction des réponses suivi colis client — boilerplate et faux positifs injection."""
#
# from __future__ import annotations
#
# import json
# import logging
# import re
# from typing import Any
#
# logger = logging.getLogger(__name__)
#
# _FALSE_INJECTION = re.compile(
#     r"prompt\s*injection|cannot follow this instruction|tentative de prompt injection|"
#     r"ressemble à une tentative|ne peux pas suivre cette instruction",
#     re.I,
# )
#
# _INJECTION_SENTENCE = re.compile(
#     r"prompt\s*injection|cannot follow|ressemble à une tentative|"
#     r"ne peux pas suivre cette instruction|instruction malveillante",
#     re.I,
# )
#
# _TRACKING_VERB = re.compile(
#     r"\b(suiv(?:re|i|s|ez)|track(?:ing)?|colis|num[eé]ro de suivi|tracking|exp[eé]dition)\b",
#     re.I,
# )
#
# _GENERIC_CONVERSATIONAL = re.compile(
#     r"(je\s+suis\s+votre\s+assistant\s+fedex|i\s+am\s+your\s+fedex\s+assistant|"
#     r"voici\s+ce\s+que\s+je\s+peux\s+faire|here\s+is\s+what\s+i\s+can\s+do|"
#     r"bien\s+cordialement.{0,40}assistant|"
#     r"fedex\s+express.{0,60}fedex\s+ground)",
#     re.I,
# )
#
# _GREETING_ONLY = re.compile(
#     r"^(bonjour|salut|hello|hi|coucou|merci|thanks|thank you|ok merci|de rien|au revoir|bye)\b",
#     re.I,
# )
#
# _FABRICATED_STATUS = re.compile(
#     r"\b(en\s+transit|livré|delivered|in\s+transit|out\s+for\s+delivery|"
#     r"prêt\s+pour\s+retrait|ready\s+for\s+pickup)\b",
#     re.I,
# )
#
# _GENERIC_ASK_TRACKING = re.compile(
#     r"(j['']?aurais?\s+besoin|il\s+me\s+faudrait|pour\s+commencer|"
#     r"i\s+would\s+need|to\s+start.{0,40}tracking|"
#     r"donnez[- ]moi.{0,30}num[eé]ro|fournir.{0,30}num[eé]ro|"
#     r"pouvez[- ]vous me fournir|pourriez[- ]vous me (?:donner|fournir).{0,40}num[eé]ro|"
#     r"sans ces d[eé]tails|je ne peux pas effectuer de recherche|"
#     r"informations n[eé]cessaires pour suivre|"
#     r"m[eé]thodes?.{0,20}suivi|fedex\s+express|fedex\s+ground|"
#     r"\[votre assistant fedex\])",
#     re.I,
# )
#
# _FEDEX_EXTERNAL_REDIRECT = re.compile(
#     r"(fedex\.com|www\.fedex\b|"
#     r"je\s+ne\s+peux\s+pas\s+suivre.{0,40}directement|"
#     r"i\s+can(?:'|no)?t\s+track.{0,40}directly|"
#     r"allez\s+sur\s+le\s+site|visit\s+the\s+(?:fedex\s+)?website|"
#     r"site\s+officiel|official\s+(?:fedex\s+)?site|"
#     r"je\s+n['']?ai\s+pas\s+acc[eè]s|i\s+don['']?t\s+have\s+access|"
#     r"application\s+mobile|mobile\s+app|"
#     r"m[eé]thodes?\s+(?:de\s+)?suivi|tracking\s+methods?)",
#     re.I,
# )
#
# _FEDEX_LOOKUP_ERROR_CODES = frozenset(
#     {"sandbox_whitelist_denied", "fedex_not_found", "fedex_unavailable"}
# )
#
#
# def contains_false_injection(text: str) -> bool:
#     if not isinstance(text, str):
#         return False
#     return bool(_FALSE_INJECTION.search(text or ""))
#
#
# def is_generic_tracking_boilerplate(
#     text: str,
#     *,
#     tracking_number: str | None,
#     message: str,
# ) -> bool:
#     """Détecte les réponses génériques qui ignorent le numéro déjà fourni."""
#     if not tracking_number or not (text or "").strip():
#         return False
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     tn_msg = extract_tracking_number(message or "")
#     if tn_msg != tracking_number and tracking_number not in (message or ""):
#         return False
#     raw = text.lower()
#     if _GENERIC_ASK_TRACKING.search(text or ""):
#         return True
#     if "besoin" in raw and "num" in raw and tracking_number not in text:
#         return True
#     if tracking_number not in text and _TRACKING_VERB.search(message or ""):
#         return True
#     return False
#
#
# def is_fedex_external_redirect_boilerplate(
#     text: str,
#     *,
#     tracking_number: str | None,
#     message: str,
#     fedex_error_code: str | None = None,
# ) -> bool:
#     """Détecte les redirections vers fedex.com quand un suivi concret est demandé."""
#     if not (text or "").strip():
#         return False
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     tn = (tracking_number or "").strip() or extract_tracking_number(message or "")
#     if not tn:
#         return False
#     if not _FEDEX_EXTERNAL_REDIRECT.search(text or ""):
#         return False
#     if fedex_error_code in _FEDEX_LOOKUP_ERROR_CODES:
#         return True
#     if tn != extract_tracking_number(message or "") and tn not in (message or ""):
#         return False
#     return bool(_TRACKING_VERB.search(message or ""))
#
#
# def is_generic_client_boilerplate(
#     text: str,
#     *,
#     message: str,
#     preferred_name: str | None = None,
# ) -> bool:
#     """Détecte réponses génériques Phase 1 (conversation + suivi)."""
#     if not (text or "").strip():
#         return False
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     tn = extract_tracking_number(message or "")
#     if tn and is_generic_tracking_boilerplate(
#         text,
#         tracking_number=tn,
#         message=message,
#     ):
#         return True
#     if tn and is_fedex_external_redirect_boilerplate(
#         text,
#         tracking_number=tn,
#         message=message,
#     ):
#         return True
#     if _GENERIC_CONVERSATIONAL.search(text or ""):
#         return True
#     if "[votre assistant fedex]" in (text or "").lower():
#         return True
#     if tn and _FABRICATED_STATUS.search(text or "") and tn in (message or ""):
#         return True
#     return False
#
#
# def _phase1_fallback_reply(
#     *,
#     message: str,
#     preferred_name: str | None,
#     ui_language: str | None,
# ) -> str:
#     from app.services.llm.providers import normalize_lang_code
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     lang = normalize_lang_code(ui_language)
#     name = (preferred_name or "").strip()
#     tn = extract_tracking_number(message or "")
#     msg = (message or "").strip()
#
#     if tn:
#         if lang == "en":
#             greeting = f"Hello {name}, " if name else ""
#             return (
#                 f"{greeting}I've noted tracking number **{tn}**. "
#                 "Live tracking will be available very soon — what else can I help you with?"
#             )
#         greeting = f"Bonjour {name}, " if name else ""
#         return (
#             f"{greeting}j'ai bien noté le numéro **{tn}**. "
#             "Le suivi en direct arrive très bientôt — que souhaitez-vous savoir d'autre ?"
#         )
#
#     if _GREETING_ONLY.match(msg.lower()):
#         if lang == "en":
#             return f"Hello {name}, how can I help you today?" if name else "Hello, how can I help you today?"
#         if lang == "ar":
#             return f"مرحباً {name}، كيف يمكنني مساعدتك؟" if name else "مرحباً، كيف يمكنني مساعدتك؟"
#         return f"Bonjour {name}, comment puis-je vous aider ?" if name else "Bonjour, comment puis-je vous aider ?"
#
#     if lang == "en":
#         return f"Sure{name and f' {name}' or ''} — tell me what you need and I'll help."
#     return "D'accord — dites-moi ce dont vous avez besoin et je vous aide."
#
#
# def repair_phase1_client_reply(
#     reply: str,
#     *,
#     message: str,
#     preferred_name: str | None = None,
#     ui_language: str | None = None,
# ) -> str:
#     """Corrige les réponses génériques Phase 1 sans FedEx ni Gemini."""
#     text = (reply or "").strip()
#     if not text:
#         return reply
#     if not is_generic_client_boilerplate(
#         text,
#         message=message,
#         preferred_name=preferred_name,
#     ):
#         return reply
#
#     logger.info("Réponse client Phase 1 générique — correction")
#
#     from app.core.config import get_settings
#     from app.services.llm.providers import call_ollama, normalize_lang_code
#
#     lang = normalize_lang_code(ui_language)
#     name = (preferred_name or "").strip()
#     name_line = f"Prénom du client : {name}.\n" if name else ""
#     retry_prompt = (
#         f"{name_line}"
#         f"Message client : {message}\n\n"
#         "Rédigez une réponse en 2 phrases maximum, ton humain et personnalisé. "
#         "Interdit : « Je suis votre assistant FedEx », listes de services FedEx, "
#         "redemander un numéro déjà dans le message, inventer un statut de colis."
#     )
#     settings = get_settings()
#     if settings.llm_enabled:
#         try:
#             regen = call_ollama(
#                 retry_prompt,
#                 preferred_name=preferred_name,
#                 ui_language=lang,
#                 intent="conversational",
#             )
#             if regen and not is_generic_client_boilerplate(
#                 regen,
#                 message=message,
#                 preferred_name=preferred_name,
#             ):
#                 return regen.strip()
#         except Exception:
#             logger.debug("Régénération Ollama Phase 1 échouée", exc_info=True)
#
#     return _phase1_fallback_reply(
#         message=message,
#         preferred_name=preferred_name,
#         ui_language=ui_language,
#     )
#
#
# def strip_injection_sentences(text: str) -> str:
#     """Supprime les phrases contenant du jargon sécurité / injection."""
#     raw = (text or "").strip()
#     if not raw:
#         return raw
#     chunks = re.split(r"(?<=[.!?])\s+|\n+", raw)
#     kept = [c.strip() for c in chunks if c.strip() and not _INJECTION_SENTENCE.search(c)]
#     return "\n\n".join(kept).strip()
#
#
# def _shipment_data_from_context(fedex_context_json: str | None) -> dict[str, Any] | None:
#     """Extrait les données colis du contexte FedEx serveur (si disponibles)."""
#     if not fedex_context_json or not fedex_context_json.strip():
#         return None
#     try:
#         payload = json.loads(fedex_context_json)
#     except (json.JSONDecodeError, TypeError):
#         return None
#     if not isinstance(payload, dict) or not payload.get("available"):
#         return None
#     shipment = payload.get("shipment")
#     if isinstance(shipment, dict) and shipment:
#         return shipment
#     tn = payload.get("tracking_number")
#     status = payload.get("status")
#     if tn and status:
#         return {
#             "tracking_number": tn,
#             "status": status,
#             "current_location": payload.get("current_location"),
#             "estimated_delivery": payload.get("estimated_delivery"),
#             "events": payload.get("events") or [],
#         }
#     return None
#
#
# def _fedex_lookup_failed(
#     fedex_error_code: str | None,
#     fedex_context_json: str | None,
# ) -> bool:
#     if fedex_error_code in ("sandbox_whitelist_denied", "fedex_not_found", "fedex_unavailable"):
#         return True
#     if not fedex_context_json:
#         return False
#     try:
#         payload = json.loads(fedex_context_json)
#     except (json.JSONDecodeError, TypeError):
#         return False
#     if not isinstance(payload, dict):
#         return False
#     if payload.get("available") is True:
#         return False
#     reason = str(payload.get("reason") or "").strip().lower()
#     return reason in {
#         "sandbox_whitelist_denied",
#         "fedex_not_found",
#         "fedex_unavailable",
#         "fedex_not_configured",
#     }
#
#
# def is_legitimate_tracking_turn(
#     message: str,
#     *,
#     tracking_number: str | None,
#     fedex_error_code: str | None,
# ) -> bool:
#     if fedex_error_code in ("sandbox_whitelist_denied", "fedex_not_found", "fedex_unavailable"):
#         return True
#     if tracking_number and _TRACKING_VERB.search(message or ""):
#         return True
#     from app.services.llm.tracking_extract import extract_tracking_number
#
#     return bool(tracking_number and extract_tracking_number(message or ""))
#
#
# def deterministic_tracking_reply(
#     *,
#     message: str,
#     tracking_number: str | None,
#     shipment_data: dict[str, Any] | None = None,
#     fedex_context_json: str | None = None,
#     fedex_error_code: str | None = None,
#     preferred_name: str | None = None,
#     ui_language: str | None = None,
#     enrich_ctx: dict[str, Any] | None = None,
# ) -> str | None:
#     """Réponse serveur sans rappeler le LLM — données FedEx déjà connues."""
#     from app.services.chat_shipment_reply import build_shipment_reply
#     from app.services.llm.providers import normalize_lang_code
#
#     shipment = shipment_data or _shipment_data_from_context(fedex_context_json)
#     if shipment:
#         ctx = enrich_ctx or {}
#         reply, _ = build_shipment_reply(
#             message or "",
#             shipment,
#             visibility_events=ctx.get("visibility_events"),
#             pod_info=ctx.get("pod_info"),
#             pod_available=ctx.get("pod_available", False),
#         )
#         if reply:
#             lang = normalize_lang_code(ui_language)
#             name = (preferred_name or "").strip()
#             if name and lang == "fr" and not reply.lower().startswith("bonjour"):
#                 return f"Bonjour {name},\n\n{reply}"
#             if name and lang == "en" and not reply.lower().startswith("hello"):
#                 return f"Hello {name},\n\n{reply}"
#             return reply
#
#     if _fedex_lookup_failed(fedex_error_code, fedex_context_json):
#         return _fallback_tracking_reply(
#             tracking_number=tracking_number,
#             preferred_name=preferred_name,
#             ui_language=ui_language,
#             fedex_context_json=fedex_context_json,
#             message=message,
#         )
#     return None
#
#
# def fedex_deterministic_reply_if_available(
#     *,
#     message: str,
#     resolved_tracking: str | None,
#     fedex_facts: Any | None = None,
#     fedex_context_json: str | None = None,
#     preferred_name: str | None = None,
#     ui_language: str | None = None,
#     reason: str = "ollama_timeout",
# ) -> str | None:
#     """Réponse suivi depuis prefetch FedEx — sans rappeler Ollama/Gemini."""
#     from app.services.client_agent.capabilities import is_phase1_chat_only
#
#     if is_phase1_chat_only():
#         return None
#
#     tracking_number = (resolved_tracking or "").strip() or None
#     error_code: str | None = None
#     shipment_data: dict[str, Any] | None = None
#     enrich_ctx: dict[str, Any] | None = None
#     context_json = (fedex_context_json or "").strip() or None
#
#     if fedex_facts is not None:
#         tracking_number = tracking_number or (getattr(fedex_facts, "tracking_number", None) or "").strip() or None
#         context_json = context_json or (getattr(fedex_facts, "fedex_context_json", None) or "").strip() or None
#         error_code = getattr(fedex_facts, "error_code", None)
#         shipment_data = getattr(fedex_facts, "shipment_data", None)
#         enrich_ctx = getattr(fedex_facts, "enrich_ctx", None)
#
#     if not tracking_number or not context_json:
#         return None
#
#     if not is_legitimate_tracking_turn(
#         message,
#         tracking_number=tracking_number,
#         fedex_error_code=error_code,
#     ):
#         return None
#
#     reply = deterministic_tracking_reply(
#         message=message,
#         tracking_number=tracking_number,
#         shipment_data=shipment_data,
#         fedex_context_json=context_json,
#         fedex_error_code=error_code,
#         preferred_name=preferred_name,
#         ui_language=ui_language,
#         enrich_ctx=enrich_ctx,
#     )
#     if not (reply or "").strip():
#         return None
#
#     tn_log = tracking_number[:4] + "…" if len(tracking_number) > 4 else tracking_number
#     logger.info("FedEx deterministic fallback (reason=%s, tracking=%s)", reason, tn_log)
#     return reply.strip()
#
#
# def _fallback_tracking_reply(
#     *,
#     tracking_number: str | None,
#     preferred_name: str | None,
#     ui_language: str | None,
#     fedex_context_json: str | None = None,
#     message: str | None = None,
# ) -> str:
#     """Réponse de secours si régénération LLM impossible."""
#     from app.services.chat_shipment_reply import build_shipment_reply
#     from app.services.llm.providers import normalize_lang_code
#
#     shipment = _shipment_data_from_context(fedex_context_json)
#     if shipment:
#         reply, _ = build_shipment_reply(message or "", shipment)
#         if reply:
#             lang = normalize_lang_code(ui_language)
#             name = (preferred_name or "").strip()
#             if name and lang == "fr" and not reply.lower().startswith("bonjour"):
#                 return f"Bonjour {name},\n\n{reply}"
#             if name and lang == "en" and not reply.lower().startswith("hello"):
#                 return f"Hello {name},\n\n{reply}"
#             return reply
#
#     lang = normalize_lang_code(ui_language)
#     name = (preferred_name or "").strip()
#     tn = tracking_number or ""
#     if lang == "en":
#         greeting = f"Hello {name}, " if name else ""
#         return (
#             f"{greeting}I couldn't find any shipment for tracking number {tn}. "
#             "Please check the number and send a valid FedEx tracking number (12 to 14 digits)."
#         )
#     if lang == "ar":
#         greeting = f"مرحباً {name}، " if name else ""
#         return (
#             f"{greeting}لم أعثر على أي شحنة برقم التتبع {tn}. "
#             "يرجى التحقق من الرقم وإرسال رقم تتبع FedEx صالح (12 إلى 14 رقماً)."
#         )
#     greeting = f"Bonjour {name}, " if name else ""
#     return (
#         f"{greeting}je n'ai trouvé aucun colis correspondant au numéro de suivi **{tn}**. "
#         "Ce numéro est peut-être incorrect ou pas encore actif. "
#         "Pourriez-vous me communiquer un numéro de suivi FedEx valide (12 à 14 chiffres) ?"
#     )
#
#
# def _regenerate_tracking_reply(
#     *,
#     tracking_number: str | None,
#     fedex_context_json: str | None,
#     ui_language: str | None,
#     preferred_name: str | None,
# ) -> str | None:
#     from app.core.config import get_settings
#     from app.services.llm.prompts import client_tracking_system_prompt
#     from app.services.llm.providers import _gemini_generate, call_ollama, normalize_lang_code
#
#     lang = normalize_lang_code(ui_language)
#     name = (preferred_name or "").strip()
#     name_line = f"Prénom du client : {name}.\n" if name else ""
#     shipment = _shipment_data_from_context(fedex_context_json)
#     if shipment:
#         instruction = (
#             "Rédigez la réponse au client en 4 à 6 phrases : résumez statut, lieu et date estimée "
#             "depuis FEDEX_DATA uniquement. Le numéro est déjà connu — ne le redemandez pas. "
#             "Terminez par une suggestion (historique, carte, POD…). "
#             "Interdit : prompt injection, attaque, sandbox, API."
#         )
#         intent = "track_package"
#     else:
#         instruction = (
#             "Rédigez la réponse au client en 3 à 5 phrases : colis introuvable pour ce numéro, "
#             "demandez poliment un numéro de suivi FedEx valide (12 à 14 chiffres). "
#             "Interdit : prompt injection, attaque, sandbox, API."
#         )
#         intent = "sandbox_whitelist_denied"
#     prompt = (
#         f"{name_line}"
#         f"Le client demande le suivi du colis {tracking_number or 'inconnu'}.\n"
#         f"Données FedEx (serveur, seule source de vérité) :\n"
#         f"{fedex_context_json or '{\"available\": false}'}\n\n"
#         f"{instruction}"
#     )
#     system = client_tracking_system_prompt(lang)
#
#     try:
#         return _gemini_generate(
#             prompt,
#             max_output_tokens=512,
#             system_instruction=system,
#             ui_language=lang,
#         )
#     except Exception:
#         logger.debug("Régénération Gemini (tracking) échouée", exc_info=True)
#
#     settings = get_settings()
#     if settings.llm_enabled:
#         try:
#             return call_ollama(
#                 prompt,
#                 fedex_context=fedex_context_json,
#                 preferred_name=preferred_name,
#                 ui_language=lang,
#                 intent=intent,
#             )
#         except Exception:
#             logger.debug("Régénération Ollama (tracking) échouée", exc_info=True)
#     return None
#
#
# def repair_client_tracking_reply(
#     reply: str,
#     *,
#     message: str,
#     tracking_number: str | None,
#     fedex_error_code: str | None,
#     fedex_context_json: str | None,
#     ui_language: str | None,
#     preferred_name: str | None = None,
#     conversation_history: str | None = None,
#     shipment_data: dict[str, Any] | None = None,
#     enrich_ctx: dict[str, Any] | None = None,
# ) -> str:
#     """Nettoie ou régénère si le LLM ignore le numéro ou parle d'injection."""
#     if not isinstance(reply, str):
#         return reply if reply else ""
#     text = (reply or "").strip()
#     if not text:
#         return reply
#     if not is_legitimate_tracking_turn(
#         message,
#         tracking_number=tracking_number,
#         fedex_error_code=fedex_error_code,
#     ):
#         return reply
#     needs_fix = (
#         contains_false_injection(text)
#         or is_generic_tracking_boilerplate(
#             text,
#             tracking_number=tracking_number,
#             message=message,
#         )
#         or is_fedex_external_redirect_boilerplate(
#             text,
#             tracking_number=tracking_number,
#             message=message,
#             fedex_error_code=fedex_error_code,
#         )
#     )
#     if not needs_fix:
#         return reply
#
#     logger.info(
#         "Réponse suivi client incorrecte — correction (tracking=%s, error=%s, fedex_ok=%s)",
#         tracking_number,
#         fedex_error_code,
#         bool(shipment_data or _shipment_data_from_context(fedex_context_json)),
#     )
#
#     deterministic = deterministic_tracking_reply(
#         message=message,
#         tracking_number=tracking_number,
#         shipment_data=shipment_data,
#         fedex_context_json=fedex_context_json,
#         fedex_error_code=fedex_error_code,
#         preferred_name=preferred_name,
#         ui_language=ui_language,
#         enrich_ctx=enrich_ctx,
#     )
#     if deterministic and not is_generic_tracking_boilerplate(
#         deterministic,
#         tracking_number=tracking_number,
#         message=message,
#     ):
#         return deterministic.strip()
#
#     lookup_failed = _fedex_lookup_failed(fedex_error_code, fedex_context_json)
#     shipment = shipment_data or _shipment_data_from_context(fedex_context_json)
#
#     if shipment and not lookup_failed:
#         from app.services.gpt.tool_synthesis import synthesize_client_from_fedex_context
#
#         synthesized = synthesize_client_from_fedex_context(
#             task=message,
#             fedex_context_json=fedex_context_json or "",
#             ui_language=ui_language or "fr",
#             preferred_name=preferred_name,
#         )
#         if synthesized and not contains_false_injection(synthesized):
#             if not is_generic_tracking_boilerplate(
#                 synthesized,
#                 tracking_number=tracking_number,
#                 message=message,
#             ):
#                 return synthesized.strip()
#
#     regen = _regenerate_tracking_reply(
#         tracking_number=tracking_number,
#         fedex_context_json=fedex_context_json,
#         ui_language=ui_language,
#         preferred_name=preferred_name,
#     )
#
#     def _acceptable(candidate: str | None) -> bool:
#         c = (candidate or "").strip()
#         if not c:
#             return False
#         if contains_false_injection(c):
#             return False
#         return not is_generic_tracking_boilerplate(
#             c,
#             tracking_number=tracking_number,
#             message=message,
#         )
#
#     if _acceptable(regen):
#         return regen.strip()
#
#     cleaned = strip_injection_sentences(text)
#     if _acceptable(cleaned):
#         return cleaned
#
#     return _fallback_tracking_reply(
#         tracking_number=tracking_number,
#         preferred_name=preferred_name,
#         ui_language=ui_language,
#         fedex_context_json=fedex_context_json,
#         message=message,
#     )
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Sécurité réponses client — stub Phase 0."""


def repair_client_tracking_reply(reply: str, **kwargs) -> str:
    return reply or ""


def is_generic_tracking_boilerplate(reply: str, **kwargs) -> bool:
    return False
