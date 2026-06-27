# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# # =============================================================================
# # LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# # Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# # =============================================================================
# # """
# # Réponses mock portail client — tests hors IA (Gemini/Ollama).
# #
# # Activer : MOCK_CLIENT_CHAT_ENABLED=true dans .env backend
# # """
# #
# # from __future__ import annotations
# #
# # import re
# # from typing import Any
# #
# # from app.services.chat_shipment_reply import INTENT_MAP_TRACKING, is_map_request
# # from app.services.llm.tracking_extract import extract_tracking_number
# # from app.services.tracking_presenter import shipment_summary
# #
# # MOCK_SOURCE = "mock"
# # WHITELIST_DEMO_TN = "881354459588"
# # DENIED_DEMO_TN = "123456789123"
# #
# # _ATTACK_PATTERNS = re.compile(
# #     r"(ignore\s+(toutes?\s+)?(tes|vos)\s+instructions|"
# #     r"contourn(e|er)\s+(les\s+)?r[eè]gles|"
# #     r"donne[- ]moi\s+(les\s+)?(cl[eé]s?\s+api|secrets?|jwt|prompt\s+syst[eè]me)|"
# #     r"r[eé]v[eè]le\s+(tes|vos)\s+instructions|"
# #     r"bypass\s+(security|rules))",
# #     re.I,
# # )
# #
# # _MOCK_SHIPMENT_WHITELIST: dict[str, Any] = {
# #     "tracking_number": WHITELIST_DEMO_TN,
# #     "status": "Ready for pickup",
# #     "status_description": "Prêt pour enlèvement",
# #     "current_location": "GREENWOOD, IN",
# #     "city": "Greenwood",
# #     "state_or_province": "IN",
# #     "country": "US",
# #     "estimated_delivery": "2026-04-22",
# #     "events": [
# #         {
# #             "at": "2026-04-21T14:30:00Z",
# #             "description": "Prêt pour enlèvement",
# #             "location": "GREENWOOD, IN",
# #         },
# #         {
# #             "at": "2026-04-21T08:00:00Z",
# #             "description": "Arrivé au centre FedEx",
# #             "location": "INDIANAPOLIS, IN",
# #         },
# #         {
# #             "at": "2026-04-20T16:00:00Z",
# #             "description": "En transit",
# #             "location": "MEMPHIS, TN",
# #         },
# #     ],
# #     "source": "mock_fedex",
# # }
# #
# #
# # def _name_line(preferred_name: str | None) -> str:
# #     name = (preferred_name or "").strip()
# #     return f"Bonjour {name},\n\n" if name else "Bonjour,\n\n"
# #
# #
# # def _mock_shipment_card(*, show_map: bool = False) -> dict[str, Any]:
# #     flags = {"show_tracking_map": show_map, "show_timeline": show_map, "max_timeline_events": 8}
# #     return shipment_summary(_MOCK_SHIPMENT_WHITELIST, **flags)
# #
# #
# # def _export_download_spec(
# #     *,
# #     session_id: int | None = None,
# #     preset: str = "tracking",
# #     tracking_numbers: list[str] | None = None,
# # ) -> dict[str, Any]:
# #     """Format attendu par ExportDownloadSpec (schemas/chat.py)."""
# #     return {
# #         "session_id": session_id or 0,
# #         "tracking_numbers": list(tracking_numbers or []),
# #         "preset": preset,
# #         "include_events": True,
# #     }
# #
# #
# #
# # def _match_agent_pdf_report(lowered: str) -> bool:
# #     return "pdf" in lowered and any(
# #         k in lowered for k in ("rapport", "résumé", "resume", "suivi", "suivis", "jour", "aujourd")
# #     )
# #
# #
# # def _match_agent_excel_account(lowered: str) -> bool:
# #     return any(k in lowered for k in ("excel", "xlsx", "export")) and any(
# #         k in lowered for k in ("compte", "tous", "historique", "suivis", "colis")
# #     )
# #
# #
# # def _match_support_ticket_request(lowered: str) -> bool:
# #     if any(k in lowered for k in ("ticket", "plainte", "réclamation", "reclamation")):
# #         return True
# #     if any(k in lowered for k in ("admin", "administrateur")) and any(
# #         k in lowered
# #         for k in ("ticket", "contacter", "contact", "demander", "vérifier", "verifier", "envoie", "envoyer")
# #     ):
# #         return True
# #     if any(k in lowered for k in ("ne reçois pas", "ne recois pas", "pas reçu", "pas recu", "ne reçoit pas")):
# #         if any(k in lowered for k in ("mail", "email", "e-mail", "courriel")):
# #             return True
# #     if any(k in lowered for k in ("problème", "probleme", "support")) and any(
# #         k in lowered for k in ("mail", "email", "livraison", "colis", "admin")
# #     ):
# #         return True
# #     return False
# #
# #
# # def _match_agent_watch_email(lowered: str) -> bool:
# #     if _match_support_ticket_request(lowered):
# #         return False
# #     if any(k in lowered for k in ("ticket", "admin", "plainte", "réclamation", "reclamation", "support")):
# #         return False
# #     if any(k in lowered for k in ("ne reçois pas", "ne recois pas", "pas reçu", "pas recu", "pourquoi")):
# #         return False
# #     return any(k in lowered for k in ("mail", "email", "e-mail", "courriel")) and any(
# #         k in lowered
# #         for k in (
# #             "chang",
# #             "emplacement",
# #             "position",
# #             "alerte",
# #             "surveill",
# #             "notif",
# #             "préven",
# #             "preven",
# #             "état",
# #             "etat",
# #         )
# #     )
# #
# #
# # def try_mock_client_response(
# #     message: str,
# #     *,
# #     agent_mode: bool = False,
# #     preferred_name: str | None = None,
# #     conversation_history: str | None = None,
# #     session_id: int | None = None,
# # ) -> dict[str, Any] | None:
# #     """
# #     Retourne un tour chat client entièrement mocké, ou None si pas de scénario reconnu.
# #     """
# #     text = (message or "").strip()
# #     if not text:
# #         return None
# #     lowered = text.lower()
# #     greeting = _name_line(preferred_name)
# #
# #     if _ATTACK_PATTERNS.search(lowered):
# #         return {
# #             "reply": (
# #                 "Je ne peux pas accéder ni divulguer :\n\n"
# #                 "- clés API\n"
# #                 "- secrets\n"
# #                 "- prompts système\n"
# #                 "- données privées\n\n"
# #                 "Cette demande est refusée."
# #             ),
# #             "source": "security",
# #             "intent": "security_blocked",
# #             "tracking_number": None,
# #             "shipment": None,
# #             "llm_provider": None,
# #             "agent_mode": False,
# #             "mock_scenario": "security_attack",
# #         }
# #
# #     if agent_mode or _match_agent_pdf_report(lowered):
# #         if _match_agent_pdf_report(lowered):
# #             export = _export_download_spec(session_id=session_id, preset="tracking_summary")
# #             return {
# #                 "reply": (
# #                     f"{greeting}"
# #                     "C'est fait — votre rapport des suivis effectués aujourd'hui est prêt."
# #                 ),
# #                 "source": MOCK_SOURCE,
# #                 "intent": "agent_summary_report",
# #                 "tracking_number": None,
# #                 "shipment": None,
# #                 "llm_provider": "mock",
# #                 "agent_mode": True,
# #                 "agent_phase": "completed",
# #                 "export_download": export,
# #                 "mock_scenario": "agent_pdf_report",
# #             }
# #
# #     if agent_mode or _match_agent_excel_account(lowered):
# #         if _match_agent_excel_account(lowered):
# #             export = _export_download_spec(session_id=session_id, preset="tracking")
# #             return {
# #                 "reply": (
# #                     f"{greeting}"
# #                     "C'est fait — l'export Excel de vos colis suivis est prêt."
# #                 ),
# #                 "source": MOCK_SOURCE,
# #                 "intent": "agent_export_excel",
# #                 "tracking_number": None,
# #                 "shipment": None,
# #                 "llm_provider": "mock",
# #                 "agent_mode": True,
# #                 "agent_phase": "completed",
# #                 "export_download": export,
# #                 "mock_scenario": "agent_excel_all",
# #             }
# #
# #     if _match_support_ticket_request(lowered):
# #         tn = extract_tracking_number(text) or extract_tracking_number(conversation_history or "")
# #         return {
# #             "reply": (
# #                 f"{greeting}"
# #                 "J'ouvre un **ticket support** pour l'équipe admin afin qu'elle vérifie "
# #                 "votre problème (e-mails de suivi, état du colis, etc.).\n\n"
# #                 "Vous recevrez la référence du dossier dans un instant."
# #             ),
# #             "source": MOCK_SOURCE,
# #             "intent": "support_ticket",
# #             "tracking_number": tn,
# #             "shipment": None,
# #             "llm_provider": "mock",
# #             "agent_mode": True,
# #             "agent_phase": "completed",
# #             "export_download": None,
# #             "mock_scenario": "agent_support_ticket",
# #             "support_message": text,
# #         }
# #
# #     if agent_mode or _match_agent_watch_email(lowered):
# #         if _match_agent_watch_email(lowered):
# #             tn = extract_tracking_number(text) or extract_tracking_number(conversation_history or "") or WHITELIST_DEMO_TN
# #             return {
# #                 "reply": (
# #                     f"{greeting}"
# #                     f"C'est fait — la surveillance est activée pour le colis **{tn}**.\n\n"
# #                     "Vous recevrez un e-mail à chaque **nouveau scan** ou **changement "
# #                     "de localisation** détecté chez FedEx (et une notification dans l'app).\n\n"
# #                     "Dites « arrête les alertes » pour désactiver la surveillance."
# #                 ),
# #                 "source": MOCK_SOURCE,
# #                 "intent": "agent_watch_shipment",
# #                 "tracking_number": tn,
# #                 "shipment": None,
# #                 "llm_provider": "mock",
# #                 "agent_mode": True,
# #                 "agent_phase": "completed",
# #                 "export_download": None,
# #                 "mock_scenario": "agent_watch_email",
# #             }
# #
# #     if not agent_mode and is_map_request(text):
# #         tn = (
# #             extract_tracking_number(text)
# #             or extract_tracking_number(conversation_history or "")
# #             or WHITELIST_DEMO_TN
# #         )
# #         return {
# #             "reply": (
# #                 f"{greeting}"
# #                 f"Voici le parcours de votre colis **{tn}** — la **carte interactive** s'affiche "
# #                 "juste en dessous avec le dernier point connu (**GREENWOOD, IN**) et les étapes "
# #                 "déjà enregistrées.\n\n"
# #                 "Souhaitez-vous aussi un **tableau chronologique** des scans ou le **statut détaillé** ?"
# #             ),
# #             "source": MOCK_SOURCE,
# #             "intent": INTENT_MAP_TRACKING,
# #             "tracking_number": tn,
# #             "shipment": _mock_shipment_card(show_map=True),
# #             "llm_provider": "mock",
# #             "agent_mode": False,
# #             "mock_scenario": "normal_map_tracking",
# #         }
# #
# #     # Suivi colis — mode normal uniquement
# #     if agent_mode:
# #         return None
# #
# #     tn = extract_tracking_number(text)
# #     if not tn:
# #         return None
# #
# #     if tn == DENIED_DEMO_TN:
# #         return {
# #             "reply": (
# #                 f"{greeting}"
# #                 f"J'ai vérifié le numéro **{tn}** dans FedEx : **aucun colis ne correspond** à ce "
# #                 "suivi pour le moment. Le numéro est peut-être incorrect, incomplet ou pas encore "
# #                 "actif dans le réseau.\n\n"
# #                 "Pouvez-vous me confirmer un numéro de suivi FedEx valide (12 à 14 chiffres) ? "
# #                 "Je pourrai vous donner le statut, le lieu et la date de livraison estimée dès qu'il "
# #                 "sera reconnu."
# #             ),
# #             "source": MOCK_SOURCE,
# #             "intent": "sandbox_whitelist_denied",
# #             "tracking_number": tn,
# #             "shipment": {
# #                 "tracking_number": tn,
# #                 "sandbox_whitelist_denied": True,
# #                 "status": None,
# #                 "current_location": None,
# #                 "estimated_delivery": None,
# #             },
# #             "llm_provider": "mock",
# #             "agent_mode": False,
# #             "mock_scenario": "normal_track_denied",
# #         }
# #
# #     if tn == WHITELIST_DEMO_TN:
# #         return {
# #             "reply": (
# #                 f"{greeting}"
# #                 f"Votre colis **{tn}** est actuellement **prêt pour enlèvement** "
# #                 "(*Ready for pickup*), dernier point connu : **GREENWOOD, IN**.\n\n"
# #                 "Souhaitez-vous que je vous montre **l'historique des scans**, la **carte du "
# #                 "trajet**, ou la **preuve de livraison** si le colis est déjà livré ?"
# #             ),
# #             "source": MOCK_SOURCE,
# #             "intent": "track_package",
# #             "tracking_number": tn,
# #             "shipment": _mock_shipment_card(show_map=False),
# #             "llm_provider": "mock",
# #             "agent_mode": False,
# #             "mock_scenario": "normal_track_whitelist",
# #         }
# #
# #     return None
# # =============================================================================
# # ACTIVE — Phase 0 stub
# # =============================================================================
# """Mock chat client — stub Phase 0."""
#
# from __future__ import annotations
#
# from typing import Any
#
#
# def try_mock_client_response(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
#     return None
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Mock chat client — stub Phase 0."""

from __future__ import annotations

from typing import Any


def try_mock_client_response(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    return None
