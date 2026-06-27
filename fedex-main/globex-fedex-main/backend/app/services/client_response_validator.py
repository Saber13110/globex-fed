# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# # =============================================================================
# # LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# # Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# # =============================================================================
# # """Validateur anti-hallucination pour réponses chat client — piloté par turn_type."""
# #
# # from __future__ import annotations
# #
# # import json
# # import re
# # from typing import Any
# #
# # from app.services.client_reply_safety import _fedex_lookup_failed, _shipment_data_from_context
# # from app.services.llm.providers import normalize_lang_code
# # from app.services.llm.tracking_extract import extract_all_tracking_numbers
# #
# # _PLACEHOLDER = re.compile(
# #     r"\[(?:nom du hub|insérer|insere|à compléter|a completer|date|lieu|ville|pays)\]",
# #     re.I,
# # )
# # _MARKDOWN_TABLE = re.compile(r"\|\s*---\s*\|")
# # _GENERIC_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
# # _TRACKING_NUMBER = re.compile(r"\b(\d{12,14})\b")
# # _BOLD_VALUE = re.compile(r"\*\*([^*]+)\*\*")
# # _ACTIVE_SHIPMENT_CLAIM = re.compile(
# #     r"\b(votre colis|your package|le colis\s+\d{12,14}|il est en transit|"
# #     r"is in transit|statut\s*[:：]\s*\*\*|currently\s+in\s+status)\b",
# #     re.I,
# # )
# # _STRICT_TURN_TYPES = frozenset(
# #     {"off_topic_general", "tracking_conversational", "tracking_format", "fedex_general"}
# # )
# # _ANCHORED_FACT_TURN_TYPES = frozenset(
# #     {"off_topic_general", "fedex_general", "tracking_conversational", "tracking_format"}
# # )
# #
# #
# # def _has_fedex_data(
# #     fedex_context_json: str | None,
# #     tool_payloads: list[dict[str, Any]] | None,
# # ) -> bool:
# #     if _shipment_data_from_context(fedex_context_json):
# #         return True
# #     for payload in tool_payloads or []:
# #         if payload.get("name") != "fedex_track_package":
# #             continue
# #         response = payload.get("response")
# #         if isinstance(response, str):
# #             try:
# #                 response = json.loads(response)
# #             except (json.JSONDecodeError, TypeError):
# #                 continue
# #         if not isinstance(response, dict):
# #             continue
# #         if response.get("available") is True or response.get("shipment"):
# #             return True
# #     return False
# #
# #
# # def _known_tracking_numbers(
# #     message: str,
# #     fedex_context_json: str | None,
# #     tool_payloads: list[dict[str, Any]] | None,
# # ) -> set[str]:
# #     known: set[str] = set(extract_all_tracking_numbers(message or ""))
# #     shipment = _shipment_data_from_context(fedex_context_json)
# #     if shipment:
# #         tn = str(shipment.get("tracking_number") or "").strip()
# #         if tn:
# #             known.add(tn)
# #     if fedex_context_json:
# #         try:
# #             payload = json.loads(fedex_context_json)
# #             if isinstance(payload, dict):
# #                 tn = str(payload.get("tracking_number") or "").strip()
# #                 if tn:
# #                     known.add(tn)
# #         except (json.JSONDecodeError, TypeError):
# #             pass
# #     for item in tool_payloads or []:
# #         if item.get("name") != "fedex_track_package":
# #             continue
# #         response = item.get("response")
# #         if isinstance(response, str):
# #             try:
# #                 response = json.loads(response)
# #             except (json.JSONDecodeError, TypeError):
# #                 continue
# #         if isinstance(response, dict):
# #             ship = response.get("shipment")
# #             if isinstance(ship, dict):
# #                 tn = str(ship.get("tracking_number") or "").strip()
# #                 if tn:
# #                     known.add(tn)
# #     return known
# #
# #
# # def _allowed_text_fragments(fedex_context_json: str | None) -> set[str]:
# #     allowed: set[str] = set()
# #     shipment = _shipment_data_from_context(fedex_context_json)
# #     if not shipment:
# #         return allowed
# #     for key in ("status", "current_location", "estimated_delivery", "actual_delivery"):
# #         val = str(shipment.get(key) or "").strip().lower()
# #         if val and val not in ("—", "-", "n/a", "non communiquée", "non communiquee"):
# #             allowed.add(val)
# #     for ev in shipment.get("events") or []:
# #         if not isinstance(ev, dict):
# #             continue
# #         for key in ("description", "location", "at", "occurred_at"):
# #             val = str(ev.get(key) or "").strip().lower()
# #             if val:
# #                 allowed.add(val)
# #                 if len(val) >= 10 and val[4] == "-":
# #                     allowed.add(val[:10])
# #     return allowed
# #
# #
# # def _event_dates(events: list[dict[str, Any]]) -> set[str]:
# #     dates: set[str] = set()
# #     for ev in events:
# #         for key in ("at", "occurred_at", "date"):
# #             val = str(ev.get(key) or "").strip()
# #             if val:
# #                 dates.add(val[:10])
# #     return dates
# #
# #
# # def _reply_has_unverified_dates(reply: str, fedex_context_json: str | None) -> bool:
# #     shipment = _shipment_data_from_context(fedex_context_json)
# #     if not shipment:
# #         return False
# #     allowed = _event_dates(shipment.get("events") or [])
# #     eta = str(shipment.get("estimated_delivery") or "").strip()
# #     if eta:
# #         allowed.add(eta[:10])
# #     actual = str(shipment.get("actual_delivery") or "").strip()
# #     if actual:
# #         allowed.add(actual[:10])
# #     for match in _GENERIC_DATE.finditer(reply or ""):
# #         if match.group(0) not in allowed:
# #             return True
# #     return False
# #
# #
# # def _has_invented_tracking_number(
# #     reply: str,
# #     *,
# #     message: str,
# #     fedex_context_json: str | None,
# #     tool_payloads: list[dict[str, Any]] | None,
# # ) -> bool:
# #     known = _known_tracking_numbers(message, fedex_context_json, tool_payloads)
# #     for match in _TRACKING_NUMBER.finditer(reply or ""):
# #         if match.group(1) not in known:
# #             return True
# #     return False
# #
# #
# # def _has_unanchored_bold_claims(reply: str, fedex_context_json: str | None) -> bool:
# #     allowed = _allowed_text_fragments(fedex_context_json)
# #     if not allowed:
# #         return False
# #     for match in _BOLD_VALUE.finditer(reply or ""):
# #         value = match.group(1).strip().lower()
# #         if len(value) < 4:
# #             continue
# #         if any(value in frag or frag in value for frag in allowed):
# #             continue
# #         if re.search(r"\b(in transit|delivered|livré|livree|pickup|transit)\b", value, re.I):
# #             return True
# #         if re.search(r",\s*[A-Z]{2}\b", match.group(1)):
# #             return True
# #     return False
# #
# #
# # def _has_anchored_package_facts_without_data(
# #     reply: str,
# #     *,
# #     fedex_context_json: str | None,
# #     tool_payloads: list[dict[str, Any]] | None,
# #     message: str,
# # ) -> bool:
# #     has_data = _has_fedex_data(fedex_context_json, tool_payloads)
# #     if has_data:
# #         return False
# #     text = reply or ""
# #     if _MARKDOWN_TABLE.search(text):
# #         return True
# #     if _has_invented_tracking_number(
# #         text, message=message, fedex_context_json=fedex_context_json, tool_payloads=tool_payloads
# #     ):
# #         return True
# #     if _ACTIVE_SHIPMENT_CLAIM.search(text):
# #         return True
# #     allowed = _allowed_text_fragments(fedex_context_json)
# #     if not allowed:
# #         for match in _BOLD_VALUE.finditer(text):
# #             value = match.group(1).strip().lower()
# #             if re.search(
# #                 r"\b(in transit|delivered|livré|livree|pickup|ready for|out for delivery)\b",
# #                 value,
# #                 re.I,
# #             ):
# #                 return True
# #             if re.search(r",\s*[A-Z]{2}\b", match.group(1)):
# #                 return True
# #     return False
# #
# #
# # def should_validate_turn(turn_type: str | None) -> bool:
# #     if not turn_type:
# #         return True
# #     if turn_type == "conversational":
# #         return False
# #     if turn_type == "automation":
# #         return False
# #     return True
# #
# #
# # def is_fabricated_tracking_reply(
# #     reply: str,
# #     *,
# #     message: str,
# #     fedex_context_json: str | None,
# #     tool_payloads: list[dict[str, Any]] | None = None,
# #     intent: str | None = None,
# #     tools_used: list[str] | None = None,
# #     turn_type: str | None = None,
# # ) -> tuple[bool, str | None]:
# #     """Détecte une réponse colis inventée ou non ancrée FedEx."""
# #     text = (reply or "").strip()
# #     if not text:
# #         return False, None
# #
# #     if turn_type == "conversational":
# #         return False, None
# #
# #     if _PLACEHOLDER.search(text):
# #         return True, "placeholder_hub"
# #
# #     has_data = _has_fedex_data(fedex_context_json, tool_payloads)
# #     lookup_failed = _fedex_lookup_failed(None, fedex_context_json)
# #
# #     if _MARKDOWN_TABLE.search(text) and not has_data:
# #         return True, "table_without_fedex"
# #
# #     tt = (turn_type or "").strip().lower()
# #
# #     if tt in _ANCHORED_FACT_TURN_TYPES or not tt:
# #         if _has_anchored_package_facts_without_data(
# #             text,
# #             fedex_context_json=fedex_context_json,
# #             tool_payloads=tool_payloads,
# #             message=message,
# #         ):
# #             if tt == "off_topic_general":
# #                 return True, "off_topic_fabricated_shipment"
# #             if tt == "fedex_general":
# #                 return True, "fedex_general_fabricated_shipment"
# #             return True, "anchored_facts_without_data"
# #
# #     if tt in ("tracking_conversational", "tracking_format") and not has_data and not lookup_failed:
# #         tools = tools_used or []
# #         if "fedex_track_package" not in tools:
# #             if _has_anchored_package_facts_without_data(
# #                 text,
# #                 fedex_context_json=fedex_context_json,
# #                 tool_payloads=tool_payloads,
# #                 message=message,
# #             ):
# #                 return True, "tracking_facts_without_tool"
# #
# #     if has_data and _reply_has_unverified_dates(text, fedex_context_json):
# #         return True, "unverified_dates"
# #
# #     if has_data and _has_unanchored_bold_claims(text, fedex_context_json):
# #         return True, "unanchored_bold_claim"
# #
# #     _ = intent
# #     return False, None
# #
# #
# # def honest_fallback_reply(
# #     message: str,
# #     *,
# #     ui_language: str | None = None,
# #     preferred_name: str | None = None,
# #     reason: str | None = None,
# #     turn_type: str | None = None,
# # ) -> str:
# #     """Réponse honnête quand le validateur bloque une hallucination."""
# #     from app.services.client_conversational import client_greeting_reply
# #
# #     lang = normalize_lang_code(ui_language)
# #     name = (preferred_name or "").strip()
# #     tt = (turn_type or "").strip().lower()
# #
# #     if tt == "conversational":
# #         return client_greeting_reply(
# #             ui_language=ui_language,
# #             preferred_name=preferred_name,
# #             message=message,
# #         )
# #
# #     if lang == "en":
# #         greeting = f"Hello {name}," if name else "Hello,"
# #         if tt == "off_topic_general":
# #             return (
# #                 f"{greeting} I don't have verified shipment data for this question. "
# #                 "If you meant a specific package, please send a FedEx tracking number "
# #                 "(12 to 14 digits). Otherwise I can help with general geography or FedEx logistics."
# #             )
# #         if tt in ("tracking_conversational", "tracking_format"):
# #             return (
# #                 f"{greeting} I couldn't verify shipment details for this request. "
# #                 "Please send a valid FedEx tracking number (12 to 14 digits) or try again."
# #             )
# #         return (
# #             f"{greeting} I don't have verified information to answer accurately. "
# #             "Please provide a valid FedEx tracking number or rephrase your question."
# #         )
# #
# #     if lang == "ar":
# #         greeting = f"مرحباً {name}،" if name else "مرحباً،"
# #         return (
# #             f"{greeting} ليس لدي معلومات موثقة للإجابة بدقة. "
# #             "يرجى إرسال رقم تتبع FedEx صالح (12 إلى 14 رقماً) أو إعادة صياغة سؤالك."
# #         )
# #
# #     greeting = f"Bonjour {name}," if name else "Bonjour,"
# #     if tt == "off_topic_general":
# #         return (
# #             f"{greeting} je n'ai pas d'information vérifiée sur un colis pour cette question. "
# #             "Si vous parlez d'un envoi précis, indiquez un numéro de suivi FedEx (12 à 14 chiffres). "
# #             "Sinon je peux répondre sur le sujet posé (géographie, services FedEx en général)."
# #         )
# #     if tt in ("tracking_conversational", "tracking_format"):
# #         return (
# #             f"{greeting} je n'ai pas pu vérifier les informations colis pour cette demande. "
# #             "Merci d'indiquer un numéro de suivi FedEx valide (12 à 14 chiffres) ou de réessayer."
# #         )
# #     return (
# #         f"{greeting} je n'ai pas cette information de manière fiable pour répondre correctement. "
# #         "Merci de préciser un numéro de suivi FedEx valide ou de reformuler votre demande."
# #     )
# #
# #
# # def validate_client_reply(
# #     reply: str,
# #     *,
# #     message: str,
# #     fedex_context_json: str | None,
# #     tool_payloads: list[dict[str, Any]] | None = None,
# #     intent: str | None = None,
# #     ui_language: str | None = None,
# #     preferred_name: str | None = None,
# #     tools_used: list[str] | None = None,
# #     turn_type: str | None = None,
# # ) -> tuple[str, bool, str | None]:
# #     """Retourne (réponse_corrigée, bloquée, raison)."""
# #     if not should_validate_turn(turn_type):
# #         return reply, False, None
# #
# #     fabricated, reason = is_fabricated_tracking_reply(
# #         reply,
# #         message=message,
# #         fedex_context_json=fedex_context_json,
# #         tool_payloads=tool_payloads,
# #         intent=intent,
# #         tools_used=tools_used,
# #         turn_type=turn_type,
# #     )
# #     if not fabricated:
# #         return reply, False, None
# #     fallback = honest_fallback_reply(
# #         message,
# #         ui_language=ui_language,
# #         preferred_name=preferred_name,
# #         reason=reason,
# #         turn_type=turn_type,
# #     )
# #     return fallback, True, reason
# # =============================================================================
# # ACTIVE — Phase 0 stub
# # =============================================================================
# """Validateur client — stub Phase 0."""
#
# from __future__ import annotations
#
# from typing import Any
#
#
# def should_validate_turn(turn_type: str | None) -> bool:
#     return False
#
#
# def validate_client_reply(
#     reply: str,
#     *,
#     message: str,
#     fedex_context_json: str | None,
#     tool_payloads: list[dict[str, Any]] | None = None,
#     intent: str | None = None,
#     ui_language: str | None = None,
#     preferred_name: str | None = None,
#     tools_used: list[str] | None = None,
#     turn_type: str | None = None,
# ) -> tuple[str, bool, str | None]:
#     return reply, False, None
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Validateur client — stub Phase 0."""

from __future__ import annotations

from typing import Any


def should_validate_turn(turn_type: str | None) -> bool:
    return False


def validate_client_reply(
    reply: str,
    *,
    message: str,
    fedex_context_json: str | None,
    tool_payloads: list[dict[str, Any]] | None = None,
    intent: str | None = None,
    ui_language: str | None = None,
    preferred_name: str | None = None,
    tools_used: list[str] | None = None,
    turn_type: str | None = None,
) -> tuple[str, bool, str | None]:
    return reply, False, None
