# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Garde-fous légers sur réponses colis (Phase 2)."""
#
# from __future__ import annotations
#
# import re
# from typing import Any
#
# from app.services.chat_shipment_reply import build_shipment_reply, validate_table_rows_match_events
# from app.services.client_agent.facts import FedExTurnFacts
# from app.services.fedex_sandbox_whitelist import CLIENT_TRACKING_NOT_FOUND_HINT
#
# _PLACEHOLDER = re.compile(
#     r"\[(?:nom du hub|insérer|insere|à compléter|a completer|date|lieu|ville|pays|Lieu de départ)\]",
#     re.I,
# )
#
# _FORBIDDEN_ERROR_JARGON = re.compile(
#     r"\b(sandbox|liste\s+blanche|whitelist|prompt\s+injection)\b",
#     re.I,
# )
#
#
# def error_fallback_reply(facts: FedExTurnFacts) -> str:
#     """Repli déterministe client-friendly quand la synthèse LLM échoue sur une erreur FedEx."""
#     tn = (facts.tracking_number or "").strip()
#     if facts.error_code in ("sandbox_whitelist_denied", "fedex_not_found"):
#         if tn:
#             return (
#                 f"Je n'ai trouvé aucun colis correspondant au numéro de suivi **{tn}**. "
#                 "Ce numéro est peut-être incorrect ou pas encore actif. "
#                 "Pourriez-vous me communiquer un numéro de suivi FedEx valide (12 à 14 chiffres) ?"
#             )
#         return CLIENT_TRACKING_NOT_FOUND_HINT
#     if facts.error_code == "fedex_unavailable":
#         return (facts.error_message or "").strip() or (
#             "Le service FedEx est temporairement indisponible. Réessayez dans quelques instants."
#         )
#     return (facts.error_message or "").strip() or (
#         "Impossible de récupérer les informations de ce colis pour le moment."
#     )
#
#
# def ensure_error_reply_safe(reply: str, facts: FedExTurnFacts) -> str:
#     """Bloque placeholders et jargon technique sur les réponses d'erreur LLM."""
#     text = (reply or "").strip()
#     if not text or _PLACEHOLDER.search(text) or _FORBIDDEN_ERROR_JARGON.search(text):
#         return error_fallback_reply(facts)
#     return text
#
#
# def _deterministic_fallback(
#     message: str,
#     shipment_data: dict[str, Any],
#     enrich_ctx: dict[str, Any],
#     *,
#     intent: str,
# ) -> str:
#     reply, _ = build_shipment_reply(
#         message,
#         shipment_data,
#         visibility_events=enrich_ctx.get("visibility_events"),
#         pod_info=enrich_ctx.get("pod_info"),
#         pod_available=enrich_ctx.get("pod_available", False),
#     )
#     return reply
#
#
# def ensure_shipment_reply_safe(
#     reply: str,
#     shipment_data: dict[str, Any],
#     enrich_ctx: dict[str, Any],
#     *,
#     message: str,
#     intent: str,
# ) -> str:
#     """
#     Si la réponse LLM est suspecte (placeholder, tableau incohérent), retomber sur le renderer serveur.
#     """
#     text = (reply or "").strip()
#     if not text or _PLACEHOLDER.search(text):
#         return _deterministic_fallback(message, shipment_data, enrich_ctx, intent=intent)
#
#     if intent == "tabular_history":
#         events = shipment_data.get("events") or []
#         if events and not validate_table_rows_match_events(text, events):
#             return _deterministic_fallback(message, shipment_data, enrich_ctx, intent=intent)
#
#     return text
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
