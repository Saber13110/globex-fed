# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# # =============================================================================
# # LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# # Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# # =============================================================================
# # """Mode Agent client : détection de tâches, questionnaire QCM, exécution automatique."""
# #
# # from __future__ import annotations
# #
# # import json
# # import logging
# # import re
# # import uuid
# # from typing import Any
# #
# # from sqlalchemy import select
# # from sqlalchemy.orm import Session
# #
# # from app.models.client_agent_pending import ClientAgentPending
# # from app.models.support_ticket import SupportTicket, SupportTicketStatus
# # from app.models.support_ticket_message import SupportTicketMessage
# # from app.models.tracking_request import TrackingRequest
# # from app.models.user import User
# # from app.schemas.client_agent import AgentQuestion, AgentQuestionnaire, AgentQuestionOption, AgentStep, AgentSuggestion
# # from app.services import fedex_service
# # from app.services.fedex_sandbox_whitelist import (
# #     CLIENT_TRACKING_NOT_FOUND_HINT,
# #     FedExSandboxWhitelistError,
# #     SANDBOX_WHITELIST_MESSAGE,
# # )
# # from app.services.chat_export_service import (
# #     generate_tracking_excel_bytes,
# #     latest_tracking_rows,
# #     session_tracking_numbers,
# #     user_recent_tracking_numbers,
# # )
# # from app.services.chat_session_context import last_session_tracking
# # from app.services.shipment_cache_service import upsert_shipment_cache
# # from app.services.email_service import is_email_configured, send_email, send_email_with_attachment
# # from app.services.llm.tracking_extract import extract_all_tracking_numbers, extract_tracking_number
# # from app.services.shipment_watch_service import (
# #     ALERT_ALL,
# #     ALERT_DELAY,
# #     ALERT_DELIVERED,
# #     ALERT_OUT_FOR_DELIVERY,
# #     deactivate_user_watches,
# #     process_single_watch,
# #     send_watch_confirmation_email,
# #     upsert_watch,
# #     finalize_watch_subscription,
# # )
# # from app.services.shipment_pdf_service import generate_multi_shipment_history_pdf, generate_shipment_history_pdf
# # from app.services.client_agent_brain import (
# #     TASK_CONVERSATION,
# #     TASK_TRACK,
# #     build_reasoning_payload,
# #     converse_in_agent_mode,
# #     plan_agent_action,
# #     synthesize_agent_reply,
# #     verify_agent_result,
# # )
# # from app.services.user_notification_service import create_user_notification, notify_admins_new_support_ticket, notify_employees_new_support_ticket
# #
# # logger = logging.getLogger(__name__)
# #
# # TASK_WATCH = "watch_shipment"
# # TASK_EXPORT = "export_excel"
# # TASK_SUPPORT = "support_ticket"
# # TASK_SUMMARY = "summary_report"
# # TASK_MULTI = "multi_track"
# # TASK_POD = "pod_delivery"
# # TASK_STOP_WATCH = "stop_watch"
# # TASK_PICKER = "task_picker"
# # # Alias importé depuis client_agent_brain (track_package)
# #
# # TASK_LABELS = {
# #     TASK_WATCH: "Surveillance automatique du colis",
# #     TASK_EXPORT: "Export Excel de l'historique",
# #     TASK_SUPPORT: "Signalement problème de livraison",
# #     TASK_SUMMARY: "Résumé / rapport PDF de l'historique",
# #     TASK_MULTI: "Suivi multi-colis",
# #     TASK_POD: "Preuve de livraison (POD) par e-mail",
# #     TASK_STOP_WATCH: "Arrêter les alertes / surveillance",
# #     TASK_TRACK: "Suivi et réponse FedEx",
# #     TASK_PICKER: "Choisir une automatisation",
# # }
# #
# # _STOP_WATCH_KEYWORDS = (
# #     "arrêt",
# #     "arrete",
# #     "arrêter",
# #     "arreter",
# #     "stop",
# #     "stopper",
# #     "désactiv",
# #     "desactiv",
# #     "annul",
# #     "cancel",
# #     "ne plus",
# #     "plus de",
# #     "couper",
# #     "supprim",
# #     "retir",
# #     "désinscri",
# #     "desinscri",
# # )
# # _STOP_WATCH_CONTEXT = ("notif", "notification", "mail", "email", "alerte", "surveill", "surveillance")
# #
# # _VALID_AGENT_TASKS = frozenset(
# #     {
# #         TASK_WATCH,
# #         TASK_EXPORT,
# #         TASK_SUPPORT,
# #         TASK_SUMMARY,
# #         TASK_MULTI,
# #         TASK_POD,
# #         TASK_STOP_WATCH,
# #         TASK_TRACK,
# #         TASK_CONVERSATION,
# #         TASK_PICKER,
# #     }
# # )
# #
# # _TASK_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
# #     (TASK_POD, ("preuve de livraison", "proof of delivery", " pod", "pod ", "preuve livraison")),
# #     (TASK_SUMMARY, ("résumé", "resume", "bilan", "synthèse", "synthese", "rapport", "performance", "historique", "chronologie", "timeline")),
# #     (TASK_WATCH, ("surveill", "alerte", "préven", "preven", "notif", "watch", "tiens-moi au courant", "tenez-moi au courant")),
# #     (TASK_EXPORT, ("export", "excel", "xlsx", "télécharger", "telecharger")),
# #     (TASK_SUPPORT, ("problème", "probleme", "réclamation", "reclamation", "ticket", "support", "plainte", "colis perdu", "retard")),
# #     (TASK_MULTI, ("compare", "plusieurs colis", "multi", "tous mes colis", "mes colis")),
# # ]
# #
# # _TRACKING_REQUEST_KEYWORDS = (
# #     "suis",
# #     "suivre",
# #     "suivi",
# #     "où est",
# #     "ou est",
# #     "statut",
# #     "localisation",
# #     "track",
# #     "tracking",
# #     "localiser",
# #     "position",
# # )
# #
# # _AUTOMATION_EXCLUDE_KEYWORDS = (
# #     "surveill",
# #     "export",
# #     "excel",
# #     "xlsx",
# #     "ticket",
# #     "pdf",
# #     "rapport",
# #     "résumé",
# #     "resume",
# #     "bilan",
# #     "preuve de livraison",
# #     " pod",
# # )
# #
# #
# # def is_simple_tracking_request(message: str) -> bool:
# #     """Demande de suivi colis (pas une automatisation watch/export/ticket)."""
# #     tn = extract_tracking_number(message)
# #     if suggest_automation_task(message, tracking_number=tn):
# #         return False
# #     if not tn:
# #         return False
# #     lowered = (message or "").strip().lower()
# #     if not lowered:
# #         return False
# #     if any(k in lowered for k in _AUTOMATION_EXCLUDE_KEYWORDS):
# #         return False
# #     if any(k in lowered for k in _WATCH_SUGGEST_KEYWORDS):
# #         return False
# #     if any(k in lowered for k in _TRACKING_REQUEST_KEYWORDS):
# #         return True
# #     if any(k in lowered for k in ("colis", "paquet", "envoi", "shipment", "package")):
# #         return True
# #     return len(lowered) < 80
# #
# #
# # def _is_stop_watch_request(lowered: str) -> bool:
# #     if not any(k in lowered for k in _STOP_WATCH_KEYWORDS):
# #         return False
# #     return any(k in lowered for k in _STOP_WATCH_CONTEXT)
# #
# #
# # def _extract_recent_count(message: str) -> int | None:
# #     """Extrait N depuis « 3 derniers colis », « les 5 derniers », etc."""
# #     lowered = (message or "").strip().lower()
# #     if not lowered:
# #         return None
# #     patterns = (
# #         r"\b(\d{1,2})\s*(?:derniers?|dernières?|derniere|last)\b",
# #         r"\b(?:les?|mes)\s*(\d{1,2})\s+(?:colis|suivis?|expéditions?|expeditions?)\b",
# #         r"\b(\d{1,2})\s+(?:colis|suivis?)\b",
# #     )
# #     for pat in patterns:
# #         m = re.search(pat, lowered)
# #         if m:
# #             return max(1, min(int(m.group(1)), 50))
# #     return None
# #
# #
# # def _resolve_follow_up_agent_plan(
# #     message: str,
# #     conversation_history: str | None,
# #     *,
# #     db: Session,
# #     session_id: int,
# #     user_id: int,
# # ) -> dict[str, Any] | None:
# #     """
# #     Comprend les demandes de suivi dans la même conversation
# #     (ex. « envoie-le par mail » après un export Excel).
# #     """
# #     msg = (message or "").strip().lower()
# #     if not conversation_history or len(msg) > 160:
# #         return None
# #
# #     hist = conversation_history.lower()
# #     mail_intent = any(
# #         k in msg
# #         for k in (
# #             "mail",
# #             "email",
# #             "e-mail",
# #             "courriel",
# #             "envoie",
# #             "envoyer",
# #             "envoyez",
# #             "renvoie",
# #             "envoi",
# #         )
# #     )
# #     if not mail_intent:
# #         return None
# #
# #     export_ctx = any(
# #         k in hist
# #         for k in (
# #             "export excel",
# #             "export prêt",
# #             "excel lancé",
# #             "historique exporter",
# #             "export_excel",
# #             "téléchargement démarre",
# #             "telechargement demarre",
# #         )
# #     )
# #     if not export_ctx:
# #         return None
# #
# #     answers: dict[str, str] = {"send_email": "yes"}
# #     count = _extract_recent_count(conversation_history) or _extract_recent_count(message)
# #     if count:
# #         answers["recent_limit"] = str(count)
# #         answers["export_scope"] = "recent"
# #     elif "cette conversation" in hist or "colis de cette conversation" in hist:
# #         answers["export_scope"] = "session"
# #     else:
# #         answers["export_scope"] = "recent"
# #         answers.setdefault("recent_limit", "3")
# #
# #     tns_preview = []
# #     if answers.get("export_scope") == "session":
# #         tns_preview = session_tracking_numbers(db, session_id, user_id)
# #     else:
# #         lim = int(answers.get("recent_limit") or 3)
# #         tns_preview = user_recent_tracking_numbers(db, user_id, lim)
# #
# #     return {
# #         "task_type": TASK_EXPORT,
# #         "action_tool": TASK_EXPORT,
# #         "objective": "Envoyer l'export Excel des colis demandés par e-mail",
# #         "plan": [
# #             "Identifier les colis concernés",
# #             "Générer le fichier Excel",
# #             "Envoyer le fichier par e-mail",
# #             "Confirmer la réception",
# #         ],
# #         "verification": "Le client reçoit l'e-mail avec le fichier Excel joint",
# #         "answers": answers,
# #         "ready_to_execute": True,
# #         "needs_clarification": False,
# #         "clarification_question": "",
# #         "assistant_intro": (
# #             f"Compris — je génère l'export Excel "
# #             f"({len(tns_preview)} colis) et je vous l'envoie à votre adresse e-mail."
# #         ),
# #         "llm_provider": "gemini",
# #     }
# #
# #
# # def open_client_support_ticket(
# #     db: Session,
# #     *,
# #     user: User,
# #     message: str,
# #     tracking_number: str | None = None,
# #     category: str = "delivery",
# #     priority: str = "medium",
# #     subject_prefix: str = "[Agent]",
# # ) -> dict[str, Any]:
# #     """Crée un ticket support client et notifie admin + employés."""
# #     tn = (tracking_number or "").strip() or extract_tracking_number(message) or ""
# #     issue_label = "Demande client"
# #     lowered = (message or "").lower()
# #     if any(k in lowered for k in ("mail", "email", "e-mail", "courriel")):
# #         issue_label = "Problème e-mails de suivi"
# #     elif any(k in lowered for k in ("retard",)):
# #         issue_label = "Retard de livraison"
# #     subject = f"{subject_prefix} {issue_label} — {tn or 'sans numéro'}"[:200]
# #     body = (message or "").strip() or "Signalement via le chat client FedEx."
# #     if tn and tn not in body:
# #         body += f"\nNuméro de suivi : {tn}"
# #     if tn:
# #         try:
# #             data = fedex_service.get_shipment(tn)
# #             body += f"\nStatut actuel : {data.get('status')} — {data.get('current_location')}"
# #         except Exception:
# #             pass
# #
# #     ticket = SupportTicket(
# #         user_id=user.id,
# #         subject=subject,
# #         category=category,
# #         priority=priority,
# #         message=body[:4000],
# #         status=SupportTicketStatus.open,
# #     )
# #     db.add(ticket)
# #     db.flush()
# #     from app.services.help_center_service import generate_ticket_number
# #
# #     ticket.ticket_number = generate_ticket_number(ticket.id)
# #     db.add(
# #         SupportTicketMessage(
# #             ticket_id=ticket.id,
# #             author_role="user",
# #             author_user_id=user.id,
# #             body=body[:4000],
# #         )
# #     )
# #     notify_admins_new_support_ticket(db, ticket, user)
# #     notify_employees_new_support_ticket(db, ticket, user)
# #     db.flush()
# #     return {
# #         "ticket_id": ticket.id,
# #         "ticket_number": ticket.ticket_number,
# #         "tracking_number": tn or None,
# #     }
# #
# #
# # def detect_agent_task(message: str) -> str | None:
# #     lowered = (message or "").strip().lower()
# #     if not lowered:
# #         return TASK_PICKER
# #
# #     if _is_stop_watch_request(lowered):
# #         return TASK_STOP_WATCH
# #
# #     if any(k in lowered for k in ("ticket",)) or (
# #         any(k in lowered for k in ("admin", "administrateur"))
# #         and any(k in lowered for k in ("ticket", "contacter", "vérifier", "verifier", "demander"))
# #     ):
# #         return TASK_SUPPORT
# #     if any(k in lowered for k in ("ne reçois pas", "ne recois pas", "pas reçu", "pas recu")) and any(
# #         k in lowered for k in ("mail", "email", "e-mail", "courriel")
# #     ):
# #         return TASK_SUPPORT
# #
# #     if any(k in lowered for k in ("pdf",)) and any(
# #         k in lowered for k in ("résumé", "resume", "historique", "chronologie", "rapport", "bilan")
# #     ):
# #         return TASK_SUMMARY
# #     if any(k in lowered for k in ("preuve", "proof", "pod")) and any(
# #         k in lowered for k in ("pdf", "mail", "email", "envoy", "envoi", "télécharger", "telecharger")
# #     ):
# #         return TASK_POD
# #     if any(k in lowered for k in ("mail", "email", "e-mail", "courriel")) and any(
# #         k in lowered for k in ("résumé", "resume", "historique", "rapport", "pdf")
# #     ):
# #         return TASK_SUMMARY
# #
# #     if any(k in lowered for k in ("export", "excel", "xlsx")) and any(
# #         k in lowered for k in ("mail", "email", "e-mail", "courriel", "envoy", "envoi")
# #     ):
# #         return TASK_EXPORT
# #
# #     for task, keywords in _TASK_PATTERNS:
# #         if any(k in lowered for k in keywords):
# #             return task
# #
# #     tn = extract_tracking_number(message)
# #     if tn and any(k in lowered for k in _WATCH_SUGGEST_KEYWORDS):
# #         return TASK_WATCH
# #     if is_simple_tracking_request(message):
# #         return TASK_TRACK
# #     return TASK_PICKER
# #
# #
# # def _classify_agent_task_llm(message: str) -> str | None:
# #     """Gemini classifie l'intention agent quand les règles ne suffisent pas."""
# #     from app.core.config import get_settings
# #
# #     settings = get_settings()
# #     if not settings.llm_enabled:
# #         return None
# #     prompt = (
# #         "Tu es un classificateur pour l'agent FedEx Globex.\n"
# #         "Retourne UNIQUEMENT un identifiant parmi:\n"
# #         "watch_shipment, stop_watch, export_excel, support_ticket, summary_report, "
# #         "multi_track, pod_delivery, none\n\n"
# #         "Règles:\n"
# #         "- stop_watch: arrêter/désactiver surveillance, notifications, mails ou alertes\n"
# #         "- watch_shipment: activer surveillance ou recevoir des alertes\n"
# #         "- none: simple question de suivi sans automatisation\n\n"
# #         f"Message: {message.strip()[:400]}\n"
# #         "Id:"
# #     )
# #     try:
# #         from app.services.llm.providers import _gemini_generate
# #
# #         raw = _gemini_generate(prompt, max_output_tokens=24, ui_language="fr").strip().lower()
# #         for token in raw.replace(",", " ").split():
# #             cleaned = token.strip(".\"' ")
# #             if cleaned in _VALID_AGENT_TASKS and cleaned != TASK_PICKER:
# #                 return cleaned
# #             if cleaned == "none":
# #                 return None
# #     except Exception:
# #         logger.debug("Classification LLM agent échouée", exc_info=True)
# #     return None
# #
# #
# # def resolve_agent_task(message: str) -> str:
# #     """Règles d'abord, puis Gemini si ambigu."""
# #     task = detect_agent_task(message)
# #     if task != TASK_PICKER:
# #         return task
# #     llm_task = _classify_agent_task_llm(message)
# #     return llm_task or TASK_PICKER
# #
# #
# # def should_route_to_client_agent(
# #     message: str,
# #     *,
# #     tracking_number: str | None = None,
# #     intent: str | None = None,
# # ) -> bool:
# #     """True si le message doit être traité en mode agent (auto-route unifiée)."""
# #     if is_simple_tracking_request(message):
# #         return False
# #     tn = tracking_number or extract_tracking_number(message)
# #     task = resolve_agent_task(message)
# #     if task and task not in (TASK_PICKER, TASK_TRACK):
# #         return True
# #     return bool(
# #         suggest_automation_task(
# #             message,
# #             tracking_number=tn,
# #             intent=intent,
# #         )
# #     )
# #
# #
# # def _infer_answers_from_message(message: str, task: str) -> dict[str, str]:
# #     """Pré-remplit le questionnaire quand la demande est déjà explicite."""
# #     lowered = (message or "").strip().lower()
# #     out: dict[str, str] = {}
# #     if task == TASK_SUMMARY:
# #         if any(k in lowered for k in ("pdf", ".pdf")):
# #             out["format"] = "pdf"
# #         if any(k in lowered for k in ("mail", "email", "e-mail", "courriel", "mon mail")):
# #             out["send_email"] = "yes"
# #         if any(k in lowered for k in ("historique", "chronologie", "timeline", "événement", "evenement", "heure")):
# #             out["scope"] = "session"
# #         if any(k in lowered for k in ("conversation", "ce colis", "mon colis", "cette session")):
# #             out["scope"] = "session"
# #         if any(k in lowered for k in ("semaine", "7 jour", "7 jours")):
# #             out["period"] = "week"
# #         elif any(k in lowered for k in ("mois", "30 jour")):
# #             out["period"] = "month"
# #         else:
# #             out.setdefault("period", "all")
# #     elif task == TASK_WATCH:
# #         if any(k in lowered for k in ("mail", "email", "e-mail", "courriel")):
# #             out["channel"] = "email_app"
# #         if any(k in lowered for k in ("app", "notification")):
# #             out.setdefault("channel", "email_app")
# #     elif task == TASK_POD:
# #         out["send_email"] = "yes"
# #         out["format"] = "pdf"
# #     elif task == TASK_STOP_WATCH:
# #         if any(k in lowered for k in ("mail", "email", "e-mail", "courriel")):
# #             out["stop_scope"] = "email"
# #         elif any(k in lowered for k in ("app", "notification", "notif")):
# #             out["stop_scope"] = "app"
# #         else:
# #             out["stop_scope"] = "all"
# #     elif task == TASK_EXPORT:
# #         count = _extract_recent_count(message)
# #         if count:
# #             out["recent_limit"] = str(count)
# #             out["export_scope"] = "recent"
# #         if any(k in lowered for k in ("dernier", "derniers", "dernières", "derniere", "recent", "récents", "recents")):
# #             out.setdefault("export_scope", "recent")
# #             out.setdefault("recent_limit", str(count or 3))
# #         if any(k in lowered for k in ("mail", "email", "e-mail", "courriel", "envoy", "envoi")):
# #             out["send_email"] = "yes"
# #         if any(k in lowered for k in ("session", "conversation", "cette conversation")):
# #             out["export_scope"] = "session"
# #         if any(k in lowered for k in ("tout mon historique", "tout l'historique", "all my")):
# #             out["export_scope"] = "all"
# #     return out
# #
# #
# # _WATCH_SUGGEST_KEYWORDS = (
# #     "surveill",
# #     "alerte",
# #     "préven",
# #     "preven",
# #     "notif",
# #     "watch",
# #     "automatiser",
# #     "automatique",
# #     "automation",
# #     "tiens-moi au courant",
# #     "tenez-moi au courant",
# #     "me tenir informé",
# #     "keep me posted",
# # )
# #
# # _SIMPLE_CHAT_MARKERS = (
# #     "où est",
# #     "ou est",
# #     "montre la carte",
# #     "affiche la carte",
# #     "tableau",
# #     "preuve de livraison",
# #     "pod",
# #     "génère une carte",
# #     "genere une carte",
# # )
# #
# #
# # def suggest_automation_task(
# #     message: str,
# #     *,
# #     tracking_number: str | None = None,
# #     intent: str | None = None,
# # ) -> str | None:
# #     """Détecte une tâche automatisable en chat normal (sans déclencher l'agent)."""
# #     lowered = (message or "").strip().lower()
# #     if not lowered:
# #         return None
# #
# #     if any(k in lowered for k in ("ticket",)) or (
# #         any(k in lowered for k in ("admin", "administrateur"))
# #         and any(k in lowered for k in ("ticket", "contacter", "vérifier", "verifier"))
# #     ):
# #         return TASK_SUPPORT
# #     if any(k in lowered for k in ("ne reçois pas", "ne recois pas", "pas reçu", "pas recu")) and any(
# #         k in lowered for k in ("mail", "email", "e-mail", "courriel")
# #     ):
# #         return TASK_SUPPORT
# #
# #     if any(k in lowered for k in _WATCH_SUGGEST_KEYWORDS):
# #         return TASK_WATCH
# #     if tracking_number and any(k in lowered for k in ("mail", "email", "e-mail", "courriel")):
# #         if any(k in lowered for k in ("préven", "preven", "alerte", "notif", "inform")):
# #             if not any(k in lowered for k in ("ticket", "admin", "pourquoi", "ne reçois pas", "ne recois pas")):
# #                 return TASK_WATCH
# #         if any(k in lowered for k in ("envoie", "envoyer")) and any(
# #             k in lowered for k in ("dès que", "des que", "chang", "emplacement", "alerte", "surveill")
# #         ):
# #             return TASK_WATCH
# #
# #     for task, keywords in _TASK_PATTERNS:
# #         if task == TASK_WATCH:
# #             continue
# #         if any(k in lowered for k in keywords):
# #             return task
# #
# #     if any(k in lowered for k in ("pdf",)) and any(k in lowered for k in ("résumé", "resume", "historique", "rapport")):
# #         return TASK_SUMMARY
# #
# #     if intent and "export" in intent:
# #         return TASK_EXPORT
# #     if intent and any(x in intent for x in ("support", "issue", "complaint")):
# #         return TASK_SUPPORT
# #
# #     if tracking_number and len(lowered) < 100:
# #         if any(m in lowered for m in _SIMPLE_CHAT_MARKERS):
# #             if not any(k in lowered for k in ("export", "excel", "ticket", "problème", "probleme", "surveill")):
# #                 return None
# #
# #     return None
# #
# #
# # def build_agent_suggestion(
# #     task: str,
# #     *,
# #     message: str,
# #     tracking_number: str | None = None,
# #     ui_language: str | None = None,
# # ) -> dict[str, str]:
# #     lang = (ui_language or "fr").lower()[:2]
# #     tn = (tracking_number or "").strip() or extract_tracking_number(message) or ""
# #     tn_bit = f" {tn}" if tn else ""
# #
# #     if lang == "en":
# #         labels = {
# #             TASK_WATCH: "Watch this parcel and email me on updates",
# #             TASK_EXPORT: "Export tracking history to Excel",
# #             TASK_SUPPORT: "Open a delivery support ticket",
# #             TASK_SUMMARY: "Weekly shipment summary report",
# #             TASK_MULTI: "Compare multiple parcels",
# #         }
# #         messages = {
# #             TASK_WATCH: "I can automate monitoring and email alerts for you.",
# #             TASK_EXPORT: "I can generate and download the Excel export automatically.",
# #             TASK_SUPPORT: "I can open a support ticket with FedEx context for you.",
# #             TASK_SUMMARY: "I can compile and send a summary of your shipments.",
# #             TASK_MULTI: "I can fetch and compare your parcels side by side.",
# #         }
# #         prefills = {
# #             TASK_WATCH: f"Watch parcel{tn_bit} and email me on every status change",
# #             TASK_EXPORT: "Export my tracking history to Excel",
# #             TASK_SUPPORT: f"I have a delivery issue on parcel{tn_bit}",
# #             TASK_SUMMARY: "Generate a summary of my recent shipments",
# #             TASK_MULTI: "Compare my parcels from this conversation",
# #         }
# #     elif lang == "ar":
# #         labels = {
# #             TASK_WATCH: "مراقبة الطرد وإرسال بريد عند التحديث",
# #             TASK_EXPORT: "تصدير سجل التتبع إلى Excel",
# #             TASK_SUPPORT: "فتح تذكرة دعم للتسليم",
# #             TASK_SUMMARY: "ملخص شحناتك",
# #             TASK_MULTI: "مقارنة عدة طرود",
# #         }
# #         messages = {
# #             TASK_WATCH: "يمكنني تفعيل المراقبة التلقائية وتنبيهات البريد.",
# #             TASK_EXPORT: "يمكنني إنشاء وتنزيل ملف Excel تلقائياً.",
# #             TASK_SUPPORT: "يمكنني فتح تذكرة دعم مع سياق FedEx.",
# #             TASK_SUMMARY: "يمكنني إعداد ملخص لشحناتك.",
# #             TASK_MULTI: "يمكنني مقارنة طرودك.",
# #         }
# #         prefills = {
# #             TASK_WATCH: f"راقب الطرد{tn_bit} وأرسل بريداً عند كل تغيير",
# #             TASK_EXPORT: "صدّر سجل التتبع إلى Excel",
# #             TASK_SUPPORT: f"لدي مشكلة تسليم للطرد{tn_bit}",
# #             TASK_SUMMARY: "أنشئ ملخصاً لشحناتي الأخيرة",
# #             TASK_MULTI: "قارن طرود هذه المحادثة",
# #         }
# #     else:
# #         labels = {
# #             TASK_WATCH: "Surveiller ce colis et m'alerter par e-mail",
# #             TASK_EXPORT: "Exporter l'historique en Excel",
# #             TASK_SUPPORT: "Ouvrir un ticket support livraison",
# #             TASK_SUMMARY: "Résumé automatique de vos expéditions",
# #             TASK_MULTI: "Comparer plusieurs colis",
# #         }
# #         messages = {
# #             TASK_WATCH: "Je peux activer la surveillance automatique avec alertes e-mail.",
# #             TASK_EXPORT: "Je peux générer et télécharger l'export Excel pour vous.",
# #             TASK_SUPPORT: "Je peux ouvrir un ticket support avec le contexte FedEx.",
# #             TASK_SUMMARY: "Je peux compiler et envoyer un bilan de vos colis.",
# #             TASK_MULTI: "Je peux interroger FedEx et comparer vos colis.",
# #         }
# #         prefills = {
# #             TASK_WATCH: f"Surveille mon colis{tn_bit} et préviens-moi par mail à chaque changement",
# #             TASK_EXPORT: "Exporte mon historique de tracking en Excel",
# #             TASK_SUPPORT: f"J'ai un problème de livraison sur le colis{tn_bit}",
# #             TASK_SUMMARY: "Génère un résumé de mes expéditions récentes",
# #             TASK_MULTI: "Compare les colis de cette conversation",
# #         }
# #
# #     return AgentSuggestion(
# #         task_type=task,
# #         label=labels.get(task, TASK_LABELS.get(task, task)),
# #         message=messages.get(task, "Cette tâche peut être automatisée en mode Agent."),
# #         prefill=prefills.get(task, message.strip() or labels.get(task, "")),
# #     ).model_dump()
# #
# #
# # def _question_options(task: str) -> list[AgentQuestion]:
# #     if task == TASK_PICKER:
# #         return [
# #             AgentQuestion(
# #                 id="task_choice",
# #                 label="Que souhaitez-vous automatiser ?",
# #                 hint="Choisissez une action — l'agent exécutera les étapes pour vous.",
# #                 options=[
# #                     AgentQuestionOption(id=TASK_WATCH, label="Surveiller un colis", description="Alertes e-mail et app"),
# #                     AgentQuestionOption(id=TASK_EXPORT, label="Exporter en Excel", description="Historique de suivi"),
# #                     AgentQuestionOption(id=TASK_SUPPORT, label="Signaler un problème", description="Créer un ticket support"),
# #                     AgentQuestionOption(id=TASK_SUMMARY, label="Résumé PDF / historique", description="Chronologie horodatée par e-mail"),
# #                     AgentQuestionOption(id=TASK_POD, label="Preuve de livraison (POD)", description="PDF par e-mail"),
# #                     AgentQuestionOption(id=TASK_STOP_WATCH, label="Arrêter les alertes", description="Désactiver mails ou surveillance"),
# #                     AgentQuestionOption(id=TASK_MULTI, label="Comparer plusieurs colis", description="Vue multi-expéditions"),
# #                 ],
# #             )
# #         ]
# #     if task == TASK_WATCH:
# #         questions = []
# #         questions.append(
# #             AgentQuestion(
# #                 id="alert_type",
# #                 label="Quand souhaitez-vous être alerté(e) ?",
# #                 options=[
# #                     AgentQuestionOption(id=ALERT_ALL, label="À chaque changement", description="Statut, lieu, étapes"),
# #                     AgentQuestionOption(id=ALERT_DELIVERED, label="À la livraison uniquement"),
# #                     AgentQuestionOption(id=ALERT_OUT_FOR_DELIVERY, label="En livraison + livré"),
# #                     AgentQuestionOption(id=ALERT_DELAY, label="Retard ou exception seulement"),
# #                 ],
# #             )
# #         )
# #         questions.append(
# #             AgentQuestion(
# #                 id="channel",
# #                 label="Comment vous prévenir ?",
# #                 options=[
# #                     AgentQuestionOption(id="email_app", label="E-mail + notification app"),
# #                     AgentQuestionOption(id="email", label="E-mail seulement"),
# #                     AgentQuestionOption(id="app", label="Notification app seulement"),
# #                 ],
# #             )
# #         )
# #         return questions
# #     if task == TASK_EXPORT:
# #         return [
# #             AgentQuestion(
# #                 id="export_scope",
# #                 label="Quel historique exporter ?",
# #                 options=[
# #                     AgentQuestionOption(id="recent", label="Mes derniers suivis"),
# #                     AgentQuestionOption(id="session", label="Cette conversation"),
# #                     AgentQuestionOption(id="all", label="Tout mon historique"),
# #                 ],
# #             ),
# #             AgentQuestion(
# #                 id="recent_limit",
# #                 label="Combien de colis récents ?",
# #                 options=[
# #                     AgentQuestionOption(id="3", label="3 derniers"),
# #                     AgentQuestionOption(id="5", label="5 derniers"),
# #                     AgentQuestionOption(id="10", label="10 derniers"),
# #                 ],
# #             ),
# #             AgentQuestion(
# #                 id="send_email",
# #                 label="Recevoir le fichier par e-mail ?",
# #                 options=[
# #                     AgentQuestionOption(id="yes", label="Oui, envoyer par e-mail"),
# #                     AgentQuestionOption(id="no", label="Non, télécharger seulement"),
# #                 ],
# #             ),
# #         ]
# #     if task == TASK_SUPPORT:
# #         return [
# #             AgentQuestion(
# #                 id="issue_type",
# #                 label="Quel type de problème ?",
# #                 options=[
# #                     AgentQuestionOption(id="delay", label="Retard de livraison"),
# #                     AgentQuestionOption(id="damaged", label="Colis endommagé"),
# #                     AgentQuestionOption(id="lost", label="Colis perdu / introuvable"),
# #                     AgentQuestionOption(id="wrong_address", label="Mauvaise adresse"),
# #                     AgentQuestionOption(id="other", label="Autre"),
# #                 ],
# #             ),
# #             AgentQuestion(
# #                 id="priority",
# #                 label="Urgence ?",
# #                 options=[
# #                     AgentQuestionOption(id="medium", label="Normale"),
# #                     AgentQuestionOption(id="high", label="Urgente"),
# #                 ],
# #             ),
# #         ]
# #     if task == TASK_SUMMARY:
# #         return [
# #             AgentQuestion(
# #                 id="scope",
# #                 label="Quels colis inclure ?",
# #                 options=[
# #                     AgentQuestionOption(id="session", label="Colis de cette conversation"),
# #                     AgentQuestionOption(id="recent", label="Mes suivis récents"),
# #                 ],
# #             ),
# #             AgentQuestion(
# #                 id="format",
# #                 label="Format du rapport ?",
# #                 options=[
# #                     AgentQuestionOption(id="pdf", label="PDF avec horodatage"),
# #                     AgentQuestionOption(id="text", label="Texte dans le chat"),
# #                 ],
# #             ),
# #             AgentQuestion(
# #                 id="period",
# #                 label="Sur quelle période ? (si historique global)",
# #                 options=[
# #                     AgentQuestionOption(id="week", label="7 derniers jours"),
# #                     AgentQuestionOption(id="month", label="30 derniers jours"),
# #                     AgentQuestionOption(id="all", label="Tout l'historique"),
# #                 ],
# #             ),
# #             AgentQuestion(
# #                 id="send_email",
# #                 label="Recevoir le rapport par e-mail ?",
# #                 options=[
# #                     AgentQuestionOption(id="yes", label="Oui, envoyer par e-mail"),
# #                     AgentQuestionOption(id="no", label="Non, afficher ici seulement"),
# #                 ],
# #             ),
# #         ]
# #     if task == TASK_STOP_WATCH:
# #         return [
# #             AgentQuestion(
# #                 id="stop_scope",
# #                 label="Que souhaitez-vous arrêter ?",
# #                 options=[
# #                     AgentQuestionOption(id="email", label="E-mails seulement"),
# #                     AgentQuestionOption(id="app", label="Notifications app seulement"),
# #                     AgentQuestionOption(id="all", label="Toute la surveillance"),
# #                 ],
# #             ),
# #         ]
# #     if task == TASK_POD:
# #         return [
# #             AgentQuestion(
# #                 id="send_email",
# #                 label="Envoyer la preuve de livraison par e-mail ?",
# #                 options=[
# #                     AgentQuestionOption(id="yes", label="Oui, PDF par e-mail"),
# #                     AgentQuestionOption(id="no", label="Non, télécharger seulement"),
# #                 ],
# #             ),
# #         ]
# #     if task == TASK_MULTI:
# #         return [
# #             AgentQuestion(
# #                 id="multi_scope",
# #                 label="Quels colis comparer ?",
# #                 options=[
# #                     AgentQuestionOption(id="session", label="Colis de cette conversation"),
# #                     AgentQuestionOption(id="recent", label="Mes 5 derniers suivis"),
# #                 ],
# #             )
# #         ]
# #     return []
# #
# #
# # def _missing_questions(task: str, answers: dict[str, str], *, has_tracking: bool) -> list[AgentQuestion]:
# #     all_q = _question_options(task)
# #     missing: list[AgentQuestion] = []
# #     if task == TASK_WATCH and not has_tracking:
# #         missing.append(
# #             AgentQuestion(
# #                 id="tracking_number",
# #                 label="Numéro de suivi FedEx",
# #                 hint="12 à 14 chiffres (ex. 881354459588)",
# #                 question_type="text",
# #                 options=[],
# #             )
# #         )
# #     for q in all_q:
# #         if q.id == "period" and answers.get("scope") == "session":
# #             continue
# #         if q.id == "recent_limit" and answers.get("export_scope") not in (None, "", "recent"):
# #             continue
# #         if q.id not in answers or not str(answers.get(q.id, "")).strip():
# #             missing.append(q)
# #     return missing
# #
# #
# # def _load_answers(raw: str) -> dict[str, str]:
# #     try:
# #         data = json.loads(raw or "{}")
# #         if isinstance(data, dict):
# #             return {str(k): str(v) for k, v in data.items()}
# #     except json.JSONDecodeError:
# #         pass
# #     return {}
# #
# #
# # def _save_pending(
# #     db: Session,
# #     *,
# #     flow_id: str,
# #     session_id: int,
# #     user_id: int,
# #     task_type: str,
# #     initial_message: str,
# #     answers: dict[str, str],
# #     status: str = "questioning",
# # ) -> ClientAgentPending:
# #     row = db.get(ClientAgentPending, flow_id)
# #     if row is None:
# #         row = ClientAgentPending(
# #             id=flow_id,
# #             session_id=session_id,
# #             user_id=user_id,
# #             task_type=task_type,
# #             initial_message=initial_message,
# #             collected_answers_json=json.dumps(answers, ensure_ascii=False),
# #             status=status,
# #         )
# #         db.add(row)
# #     else:
# #         row.collected_answers_json = json.dumps(answers, ensure_ascii=False)
# #         row.task_type = task_type
# #         row.status = status
# #     db.flush()
# #     return row
# #
# #
# # def _resolve_tracking(message: str, answers: dict[str, str], session_id: int, user_id: int, db: Session) -> str | None:
# #     tn = (answers.get("tracking_number") or "").strip()
# #     if tn:
# #         return tn
# #     tn = extract_tracking_number(message)
# #     if tn:
# #         return tn
# #     nums = session_tracking_numbers(db, session_id, user_id)
# #     if len(nums) == 1:
# #         return nums[0]
# #     if len(nums) > 1:
# #         return nums[-1]
# #     return last_session_tracking(db, session_id=session_id, user_id=user_id)
# #
# #
# # def _build_questionnaire_response(
# #     *,
# #     flow_id: str,
# #     task: str,
# #     intro: str,
# #     questions: list[AgentQuestion],
# #     llm_provider: str | None = None,
# #     brain_plan: dict[str, Any] | None = None,
# # ) -> dict[str, Any]:
# #     result = {
# #         "reply": intro,
# #         "source": "agent",
# #         "intent": f"agent_{task}",
# #         "agent_mode": True,
# #         "agent_phase": "questionnaire",
# #         "agent_questionnaire": AgentQuestionnaire(
# #             flow_id=flow_id,
# #             task_type=task,
# #             task_label=TASK_LABELS.get(task, task),
# #             intro=intro,
# #             questions=questions,
# #         ).model_dump(),
# #         "agent_steps": [],
# #         "shipment": None,
# #         "tracking_number": None,
# #         "llm_provider": llm_provider,
# #     }
# #     if brain_plan:
# #         result["agent_reasoning"] = build_reasoning_payload(
# #             brain_plan,
# #             task_label=TASK_LABELS.get(task, task),
# #         )
# #         result["agent_steps"] = _reasoning_steps_from_plan(brain_plan, None, "")
# #     return result
# #
# #
# # def _enrich_agent_reply_with_gemini(
# #     result: dict[str, Any],
# #     *,
# #     user_message: str,
# #     task: str,
# #     ui_language: str = "fr",
# #     brain_plan: dict[str, Any] | None = None,
# # ) -> dict[str, Any]:
# #     """Reformule le résultat technique, vérifie l'objectif, enrichit le raisonnement."""
# #     technical = str(result.get("reply") or "")
# #     steps = result.get("agent_steps") or []
# #     steps_txt = "\n".join(
# #         f"- {s.get('label', '')} ({s.get('status', '')})" for s in steps if isinstance(s, dict)
# #     )
# #
# #     verified: bool | None = None
# #     verification_note = ""
# #     if brain_plan and brain_plan.get("objective"):
# #         check = verify_agent_result(
# #             objective=brain_plan.get("objective") or "",
# #             verification=brain_plan.get("verification") or "",
# #             task=task,
# #             technical_result=technical,
# #             steps_summary=steps_txt,
# #             ui_language=ui_language,
# #         )
# #         verified = check.get("verified")
# #         verification_note = check.get("note") or ""
# #         if verified is False and verification_note:
# #             technical = f"{technical}\n\n⚠️ {verification_note}"
# #
# #     natural = synthesize_agent_reply(
# #         user_message=user_message,
# #         task=task,
# #         task_label=TASK_LABELS.get(task, task),
# #         technical_reply=technical,
# #         steps_summary=steps_txt,
# #         ui_language=ui_language,
# #     )
# #     if natural:
# #         result["reply"] = natural
# #     elif verified is False and verification_note:
# #         result["reply"] = technical
# #
# #     from app.services.client_reply_safety import repair_client_tracking_reply
# #     from app.services.llm.tracking_extract import extract_tracking_number
# #
# #     tn = result.get("tracking_number") or extract_tracking_number(user_message)
# #     result["reply"] = repair_client_tracking_reply(
# #         str(result.get("reply") or ""),
# #         message=user_message,
# #         tracking_number=tn,
# #         fedex_error_code=result.get("tracking_error_code"),
# #         fedex_context_json=result.get("fedex_context_json"),
# #         ui_language=ui_language,
# #         preferred_name=None,
# #     )
# #
# #     result["llm_provider"] = result.get("llm_provider") or "gemini"
# #     result["source"] = "agent+gemini"
# #
# #     if brain_plan:
# #         result["agent_reasoning"] = build_reasoning_payload(
# #             brain_plan,
# #             task_label=TASK_LABELS.get(task, task),
# #             verified=verified,
# #             verification_note=verification_note,
# #         )
# #         reasoning_steps = _reasoning_steps_from_plan(brain_plan, verified, verification_note)
# #         if reasoning_steps:
# #             existing = result.get("agent_steps") or []
# #             result["agent_steps"] = reasoning_steps + existing
# #
# #     return result
# #
# #
# # def _reasoning_steps_from_plan(
# #     brain_plan: dict[str, Any],
# #     verified: bool | None,
# #     verification_note: str,
# # ) -> list[dict[str, Any]]:
# #     """Étapes visibles OBJECTIF → PLAN → ACTION → VÉRIFICATION."""
# #     steps: list[dict[str, Any]] = []
# #     objective = (brain_plan.get("objective") or "").strip()
# #     if objective:
# #         steps.append(AgentStep(label="Objectif", status="done", detail=objective[:200]).model_dump())
# #
# #     plan = brain_plan.get("plan") or []
# #     if plan:
# #         plan_txt = " → ".join(str(p) for p in plan[:5])
# #         steps.append(AgentStep(label="Plan", status="done", detail=plan_txt[:240]).model_dump())
# #
# #     action = brain_plan.get("action_tool") or brain_plan.get("task_type") or ""
# #     if action:
# #         steps.append(
# #             AgentStep(
# #                 label="Action",
# #                 status="done",
# #                 detail=TASK_LABELS.get(action, action),
# #             ).model_dump()
# #         )
# #
# #     verif = (brain_plan.get("verification") or "").strip()
# #     if verif or verified is not None:
# #         if verified is True:
# #             status = "done"
# #             detail = verification_note or verif or "Demande satisfaite"
# #         elif verified is False:
# #             status = "warning"
# #             detail = verification_note or verif or "Résultat partiel"
# #         else:
# #             status = "running"
# #             detail = verif or "Vérification en cours"
# #         steps.append(AgentStep(label="Vérification", status=status, detail=detail[:200]).model_dump())
# #
# #     return steps
# #
# #
# # def _agent_conversation_response(
# #     db: Session,
# #     *,
# #     user: User,
# #     session_id: int,
# #     message: str,
# #     conversation_history: str | None,
# #     ui_language: str = "fr",
# #     brain_intro: str | None = None,
# # ) -> dict[str, Any]:
# #     """Réponse conversationnelle FedEx via Gemini (cerveau agent)."""
# #     from app.services.llm.fedex_context import resolve_client_fedex_lookup
# #
# #     answers: dict[str, str] = {}
# #     tn = _resolve_tracking(message, answers, session_id, user.id, db)
# #     shipment_for_client = None
# #     fedex_ctx: str | None = None
# #     tracking_error_code: str | None = None
# #     llm_intent = "track_package"
# #
# #     if tn:
# #         lookup = resolve_client_fedex_lookup(tn)
# #         fedex_ctx = lookup.fedex_context_json
# #         tracking_error_code = lookup.tracking_error_code
# #         llm_intent = lookup.llm_intent
# #
# #     reply, llm_provider = converse_in_agent_mode(
# #         message,
# #         conversation_history=conversation_history,
# #         fedex_context_json=fedex_ctx,
# #         ui_language=ui_language,
# #         preferred_name=user.full_name,
# #         intent=llm_intent,
# #         tracking_number=tn,
# #     )
# #     if not reply:
# #         reply = brain_intro or "Je suis votre agent FedEx. Comment puis-je vous aider sur vos colis ?"
# #     elif brain_intro and brain_intro not in reply and not (
# #         "prompt injection" in reply.lower() or "ne peux pas suivre cette instruction" in reply.lower()
# #     ):
# #         reply = f"{brain_intro}\n\n{reply}"
# #
# #     from app.services.client_reply_safety import repair_client_tracking_reply
# #
# #     reply = repair_client_tracking_reply(
# #         reply,
# #         message=message,
# #         tracking_number=tn,
# #         fedex_error_code=tracking_error_code,
# #         fedex_context_json=fedex_ctx,
# #         ui_language=ui_language,
# #         preferred_name=user.full_name,
# #         conversation_history=conversation_history,
# #     )
# #
# #     return {
# #         "reply": reply,
# #         "source": "agent+llm",
# #         "intent": "agent_conversation",
# #         "agent_mode": True,
# #         "agent_phase": "completed",
# #         "agent_questionnaire": None,
# #         "agent_steps": [],
# #         "shipment": shipment_for_client,
# #         "tracking_number": tn,
# #         "tracking_error_code": tracking_error_code,
# #         "fedex_context_json": fedex_ctx,
# #         "export_download": None,
# #         "llm_provider": llm_provider,
# #     }
# #
# #
# # def process_agent_message(
# #     db: Session,
# #     *,
# #     user: User,
# #     message: str,
# #     session_id: int,
# #     agent_answers: dict[str, str] | None = None,
# #     agent_flow_id: str | None = None,
# #     ui_language: str = "fr",
# #     conversation_history: str | None = None,
# # ) -> dict[str, Any]:
# #     msg = (message or "").strip()
# #     answers_in = dict(agent_answers or {})
# #
# #     if agent_flow_id:
# #         pending = db.get(ClientAgentPending, agent_flow_id)
# #         if pending is None or pending.user_id != user.id or pending.session_id != session_id:
# #             return _build_questionnaire_response(
# #                 flow_id=str(uuid.uuid4()),
# #                 task=TASK_PICKER,
# #                 intro="Le questionnaire précédent a expiré. Choisissez à nouveau ce que l'agent doit faire.",
# #                 questions=_question_options(TASK_PICKER),
# #             )
# #         task = pending.task_type
# #         answers = _load_answers(pending.collected_answers_json)
# #         answers.update({k: v for k, v in answers_in.items() if v})
# #         answers.update(_infer_answers_from_message(pending.initial_message or msg, task))
# #         if answers.get("task_choice"):
# #             task = answers["task_choice"]
# #             pending.task_type = task
# #         tracking = _resolve_tracking(pending.initial_message or msg, answers, session_id, user.id, db)
# #         if tracking:
# #             answers["tracking_number"] = tracking
# #         missing = _missing_questions(task, answers, has_tracking=bool(tracking))
# #         if missing:
# #             flow_id = pending.id
# #             _save_pending(
# #                 db,
# #                 flow_id=flow_id,
# #                 session_id=session_id,
# #                 user_id=user.id,
# #                 task_type=task,
# #                 initial_message=pending.initial_message or msg,
# #                 answers=answers,
# #             )
# #             return _build_questionnaire_response(
# #                 flow_id=flow_id,
# #                 task=task,
# #                 intro="Merci — quelques précisions avant que je lance l'automatisation :",
# #                 questions=missing,
# #                 brain_plan=plan_agent_action(
# #                     pending.initial_message or msg,
# #                     conversation_history=conversation_history,
# #                     session_tracking_numbers=session_tracking_numbers(db, session_id, user.id),
# #                     user_name=user.full_name or user.email,
# #                     ui_language=ui_language,
# #                 ),
# #             )
# #         pending.status = "executing"
# #         pending.collected_answers_json = json.dumps(answers, ensure_ascii=False)
# #         db.flush()
# #         result = _execute_task(
# #             db,
# #             user=user,
# #             session_id=session_id,
# #             task=task,
# #             answers=answers,
# #             initial_message=pending.initial_message or msg,
# #         )
# #         pending.status = "done"
# #         flow_brain = plan_agent_action(
# #             pending.initial_message or msg,
# #             conversation_history=conversation_history,
# #             session_tracking_numbers=session_tracking_numbers(db, session_id, user.id),
# #             user_name=user.full_name or user.email,
# #             ui_language=ui_language,
# #         )
# #         return _enrich_agent_reply_with_gemini(
# #             result,
# #             user_message=pending.initial_message or msg,
# #             task=task,
# #             ui_language=ui_language,
# #             brain_plan=flow_brain,
# #         )
# #
# #     follow_up = _resolve_follow_up_agent_plan(
# #         msg,
# #         conversation_history,
# #         db=db,
# #         session_id=session_id,
# #         user_id=user.id,
# #     )
# #     if follow_up and follow_up.get("ready_to_execute"):
# #         task = follow_up["task_type"]
# #         answers_fu = dict(follow_up.get("answers") or {})
# #         answers_fu.update(_infer_answers_from_message(msg, task))
# #         result = _execute_task(
# #             db,
# #             user=user,
# #             session_id=session_id,
# #             task=task,
# #             answers=answers_fu,
# #             initial_message=msg,
# #         )
# #         return _enrich_agent_reply_with_gemini(
# #             result,
# #             user_message=msg,
# #             task=task,
# #             ui_language=ui_language,
# #             brain_plan=follow_up,
# #         )
# #
# #     brain_plan = plan_agent_action(
# #         msg,
# #         conversation_history=conversation_history,
# #         session_tracking_numbers=session_tracking_numbers(db, session_id, user.id),
# #         user_name=user.full_name or user.email,
# #         ui_language=ui_language,
# #     ) if msg else None
# #
# #     brain_intro = (brain_plan or {}).get("assistant_intro") or ""
# #     brain_llm = (brain_plan or {}).get("llm_provider")
# #
# #     if brain_plan and brain_plan.get("task_type") in (TASK_CONVERSATION, TASK_TRACK):
# #         return _agent_conversation_response(
# #             db,
# #             user=user,
# #             session_id=session_id,
# #             message=msg,
# #             conversation_history=conversation_history,
# #             ui_language=ui_language,
# #             brain_intro=brain_intro,
# #         )
# #
# #     if brain_plan and brain_plan.get("task_type") in _VALID_AGENT_TASKS and brain_plan["task_type"] != TASK_PICKER:
# #         task = brain_plan["task_type"]
# #         answers_in.update(brain_plan.get("answers") or {})
# #     else:
# #         task = resolve_agent_task(msg)
# #
# #     if task == TASK_PICKER and answers_in.get("task_choice"):
# #         task = answers_in["task_choice"]
# #
# #     answers_in.update(_infer_answers_from_message(msg, task))
# #
# #     tracking = _resolve_tracking(msg, answers_in, session_id, user.id, db)
# #     if tracking:
# #         answers_in["tracking_number"] = tracking
# #
# #     if (
# #         brain_plan
# #         and brain_plan.get("needs_clarification")
# #         and brain_plan.get("clarification_question")
# #         and not brain_plan.get("ready_to_execute")
# #     ):
# #         flow_id = str(uuid.uuid4())
# #         _save_pending(
# #             db,
# #             flow_id=flow_id,
# #             session_id=session_id,
# #             user_id=user.id,
# #             task_type=task,
# #             initial_message=msg,
# #             answers=answers_in,
# #         )
# #         intro = f"{brain_intro}\n\n{brain_plan['clarification_question']}".strip()
# #         clarify_q = [
# #             AgentQuestion(
# #                 id="clarification",
# #                 label=brain_plan["clarification_question"],
# #                 question_type="text",
# #                 options=[],
# #                 required=True,
# #             )
# #         ]
# #         return _build_questionnaire_response(
# #             flow_id=flow_id,
# #             task=task,
# #             intro=intro,
# #             questions=clarify_q,
# #             llm_provider=brain_llm,
# #             brain_plan=brain_plan,
# #         )
# #
# #     if task == TASK_PICKER:
# #         if is_simple_tracking_request(msg):
# #             return _agent_conversation_response(
# #                 db,
# #                 user=user,
# #                 session_id=session_id,
# #                 message=msg,
# #                 conversation_history=conversation_history,
# #                 ui_language=ui_language,
# #                 brain_intro=brain_intro,
# #             )
# #         flow_id = str(uuid.uuid4())
# #         _save_pending(
# #             db,
# #             flow_id=flow_id,
# #             session_id=session_id,
# #             user_id=user.id,
# #             task_type=TASK_PICKER,
# #             initial_message=msg,
# #             answers=answers_in,
# #         )
# #         intro = brain_intro or (
# #             "Bonjour — je suis votre **agent FedEx Globex**. "
# #             "Dites-moi ce que vous voulez automatiser, ou choisissez ci-dessous :"
# #         )
# #         return _build_questionnaire_response(
# #             flow_id=flow_id,
# #             task=TASK_PICKER,
# #             intro=intro,
# #             questions=_question_options(TASK_PICKER),
# #             llm_provider=brain_llm,
# #             brain_plan=brain_plan,
# #         )
# #
# #     missing = _missing_questions(task, answers_in, has_tracking=bool(tracking))
# #     brain_ready = bool(brain_plan and brain_plan.get("ready_to_execute") and not brain_plan.get("needs_clarification"))
# #
# #     if missing and not brain_ready:
# #         flow_id = str(uuid.uuid4())
# #         _save_pending(
# #             db,
# #             flow_id=flow_id,
# #             session_id=session_id,
# #             user_id=user.id,
# #             task_type=task,
# #             initial_message=msg,
# #             answers=answers_in,
# #         )
# #         intro = brain_intro or (
# #             f"J'ai compris votre demande : **{TASK_LABELS.get(task, task)}**.\n\n"
# #             "Avant d'exécuter automatiquement, confirmez ces choix :"
# #         )
# #         if brain_plan and brain_plan.get("clarification_question"):
# #             intro = f"{brain_intro}\n\n{brain_plan['clarification_question']}".strip()
# #         return _build_questionnaire_response(
# #             flow_id=flow_id,
# #             task=task,
# #             intro=intro,
# #             questions=missing,
# #             llm_provider=brain_llm,
# #             brain_plan=brain_plan,
# #         )
# #
# #     result = _execute_task(
# #         db,
# #         user=user,
# #         session_id=session_id,
# #         task=task,
# #         answers=answers_in,
# #         initial_message=msg,
# #     )
# #     return _enrich_agent_reply_with_gemini(
# #         result,
# #         user_message=msg,
# #         task=task,
# #         ui_language=ui_language,
# #         brain_plan=brain_plan,
# #     )
# #
# #
# # def _execute_task(
# #     db: Session,
# #     *,
# #     user: User,
# #     session_id: int,
# #     task: str,
# #     answers: dict[str, str],
# #     initial_message: str,
# # ) -> dict[str, Any]:
# #     steps: list[AgentStep] = []
# #     shipment_for_client: dict[str, Any] | None = None
# #     tracking_number: str | None = None
# #     export_download: dict[str, Any] | None = None
# #     reply_parts: list[str] = []
# #
# #     if task == TASK_STOP_WATCH:
# #         scope = answers.get("stop_scope") or "email"
# #         tn = (answers.get("tracking_number") or "").strip() or _resolve_tracking(
# #             initial_message, answers, session_id, user.id, db
# #         )
# #         steps.append(AgentStep(label="Arrêt des alertes", status="running"))
# #         updated = deactivate_user_watches(
# #             db,
# #             user_id=user.id,
# #             tracking_number=tn,
# #             stop_email=scope in ("email", "all"),
# #             stop_app=scope == "app",
# #             stop_all=scope == "all",
# #         )
# #         if not updated:
# #             reply_parts.append(
# #                 "Aucune surveillance active trouvée pour votre compte"
# #                 + (f" sur le colis `{tn}`." if tn else ".")
# #             )
# #             steps.append(AgentStep(label="Aucune surveillance active", status="warning"))
# #         else:
# #             labels = {
# #                 "email": "les e-mails d'alerte",
# #                 "app": "les notifications app",
# #                 "all": "toute la surveillance",
# #             }
# #             what = labels.get(scope, "les alertes")
# #             tns = ", ".join(f"`{w.tracking_number}`" for w in updated)
# #             steps.append(AgentStep(label="Alertes mises à jour", status="done", detail=tns))
# #             reply_parts.append(f"**C'est fait** — j'ai arrêté {what} pour : {tns}.")
# #             if scope == "email":
# #                 reply_parts.append("\nLa surveillance reste active en notifications app si vous le souhaitez.")
# #             create_user_notification(
# #                 db,
# #                 user_id=user.id,
# #                 type="tracking_update",
# #                 title="Alertes colis modifiées",
# #                 message=f"Alertes mises à jour ({what}) pour {len(updated)} colis.",
# #                 related_tracking_number=updated[0].tracking_number if updated else "",
# #                 link="/notifications",
# #             )
# #
# #     elif task == TASK_WATCH:
# #         tn = (answers.get("tracking_number") or "").strip() or extract_tracking_number(initial_message)
# #         if not tn:
# #             return _build_questionnaire_response(
# #                 flow_id=str(uuid.uuid4()),
# #                 task=task,
# #                 intro="Il me manque le numéro de suivi pour activer la surveillance.",
# #                 questions=[
# #                     AgentQuestion(
# #                         id="tracking_number",
# #                         label="Numéro de suivi FedEx",
# #                         question_type="text",
# #                         options=[],
# #                     )
# #                 ],
# #             )
# #         tracking_number = tn
# #         alert_type = answers.get("alert_type") or ALERT_ALL
# #         channel = answers.get("channel") or "email_app"
# #         notify_email = channel in ("email", "email_app")
# #         notify_in_app = channel in ("app", "email_app")
# #
# #         steps.append(AgentStep(label="Activation surveillance", status="running", detail=tn))
# #         try:
# #             watch = upsert_watch(
# #                 db,
# #                 user_id=user.id,
# #                 tracking_number=tn,
# #                 alert_type=alert_type,
# #                 notify_email=notify_email,
# #                 notify_in_app=notify_in_app,
# #             )
# #         except FedExSandboxWhitelistError:
# #             return {
# #                 "reply": (
# #                     f"**Surveillance impossible** pour `{tn}`.\n\n"
# #                     f"{SANDBOX_WHITELIST_MESSAGE}\n\n"
# #                     "Exemples valides en sandbox : `881354459588`, `397773675776`."
# #                 ),
# #                 "agent_steps": [
# #                     AgentStep(label="Numéro non autorisé (sandbox FedEx)", status="error", detail=tn),
# #                 ],
# #                 "shipment": None,
# #                 "export_download": None,
# #                 "tracking_number": tn,
# #             }
# #         steps.append(AgentStep(label="Surveillance enregistrée", status="done"))
# #
# #         steps.append(AgentStep(label="Vérification FedEx", status="running"))
# #         try:
# #             data = fedex_service.get_shipment(tn)
# #             upsert_shipment_cache(db, data)
# #             finalize_watch_subscription(db, watch, data)
# #             process_single_watch(db, watch)
# #             steps.append(AgentStep(label="Statut FedEx récupéré", status="done", detail=data.get("status")))
# #         except FedExSandboxWhitelistError:
# #             steps.append(
# #                 AgentStep(label="Numéro non autorisé (sandbox FedEx)", status="error", detail=tn)
# #             )
# #             reply_parts.append(
# #                 f"**Surveillance enregistrée** pour `{tn}`, mais FedEx sandbox refuse ce numéro.\n"
# #                 f"{SANDBOX_WHITELIST_MESSAGE}"
# #             )
# #         except Exception as exc:
# #             steps.append(AgentStep(label="FedEx temporairement indisponible", status="warning", detail=str(exc)[:80]))
# #
# #         if notify_email:
# #             steps.append(AgentStep(label="E-mail de confirmation", status="running"))
# #             sent = send_watch_confirmation_email(user, watch)
# #             steps.append(
# #                 AgentStep(
# #                     label="E-mail envoyé" if sent else "E-mail non envoyé (SMTP)",
# #                     status="done" if sent else "warning",
# #                 )
# #             )
# #
# #         channel_txt = {"email_app": "e-mail et notifications app", "email": "e-mail", "app": "notifications app"}.get(
# #             channel, "e-mail et app"
# #         )
# #         reply_parts.append(
# #             f"**Surveillance activée** pour le colis `{tn}`.\n"
# #             f"- Alertes : {channel_txt}\n"
# #             f"- Déclenchement : selon votre choix ({alert_type})\n"
# #             f"- L'agent vérifie automatiquement le statut en arrière-plan."
# #         )
# #         if not is_email_configured() and notify_email:
# #             reply_parts.append("\n_Note : SMTP non configuré — les e-mails seront activés dès que le serveur mail sera prêt._")
# #
# #     elif task == TASK_EXPORT:
# #         scope = answers.get("export_scope") or "recent"
# #         send_mail = answers.get("send_email") == "yes"
# #         recent_limit = max(1, min(int(answers.get("recent_limit") or 3), 50))
# #
# #         steps.append(AgentStep(label="Préparation export Excel", status="running"))
# #         if scope == "session":
# #             tns = session_tracking_numbers(db, session_id, user.id)
# #             tns = tns[:recent_limit]
# #         elif scope == "recent":
# #             tns = user_recent_tracking_numbers(db, user.id, recent_limit)
# #         else:
# #             tns = user_recent_tracking_numbers(db, user.id, 200)
# #
# #         rows = latest_tracking_rows(
# #             db,
# #             user_id=user.id,
# #             tracking_numbers=tns if tns else None,
# #             session_id=session_id if scope == "session" and not tns else None,
# #             limit=max(len(tns), recent_limit, 1),
# #         )
# #         if scope == "recent" and tns:
# #             rows = [r for r in rows if r.tracking_number in tns]
# #             rows.sort(key=lambda r: tns.index(r.tracking_number) if r.tracking_number in tns else 999)
# #
# #         tns_final = [r.tracking_number for r in rows] if rows else tns
# #         export_download = None if send_mail else {
# #             "session_id": session_id,
# #             "tracking_numbers": tns_final,
# #             "preset": "tracking",
# #             "include_events": True,
# #         }
# #
# #         if rows:
# #             steps.append(AgentStep(label="Génération Excel", status="running"))
# #             try:
# #                 excel_bytes = generate_tracking_excel_bytes(db, rows, include_events=True)
# #                 steps.append(AgentStep(label="Export prêt", status="done", detail=f"{len(rows)} colis"))
# #
# #                 if send_mail and is_email_configured() and user.email:
# #                     steps.append(AgentStep(label="Envoi e-mail avec Excel", status="running"))
# #                     send_email_with_attachment(
# #                         to=user.email,
# #                         subject=f"[Globex FedEx] Export Excel — {len(rows)} colis",
# #                         body_text=(
# #                             f"Bonjour {user.full_name or ''},\n\n"
# #                             f"Veuillez trouver ci-joint l'export Excel de vos {len(rows)} derniers colis suivis.\n\n"
# #                             f"— Agent FedEx Globex"
# #                         ),
# #                         attachment_bytes=excel_bytes,
# #                         attachment_filename="export-suivi-fedex.xlsx",
# #                     )
# #                     steps.append(AgentStep(label="E-mail envoyé", status="done", detail=user.email))
# #                     create_user_notification(
# #                         db,
# #                         user_id=user.id,
# #                         type="document_ready",
# #                         title="Export Excel envoyé",
# #                         message=f"Fichier Excel envoyé à {user.email} ({len(rows)} colis).",
# #                         related_tracking_number=rows[0].tracking_number if rows else "",
# #                         link="/notifications",
# #                     )
# #                     reply_parts.append(
# #                         f"**Export Excel envoyé** à `{user.email}` — **{len(rows)} colis** inclus."
# #                     )
# #                 elif send_mail:
# #                     steps.append(AgentStep(label="E-mail non configuré", status="warning"))
# #                     export_download = {
# #                         "session_id": session_id,
# #                         "tracking_numbers": tns_final,
# #                         "preset": "tracking",
# #                         "include_events": True,
# #                     }
# #                     reply_parts.append(
# #                         f"**Export Excel prêt** — {len(rows)} colis.\n"
# #                         "_SMTP non configuré : téléchargement lancé à la place._"
# #                     )
# #                 else:
# #                     reply_parts.append(
# #                         f"**Export Excel lancé** — {len(rows)} numéro(s) de suivi inclus.\n"
# #                         "Le téléchargement démarre automatiquement."
# #                     )
# #             except Exception as exc:
# #                 steps.append(AgentStep(label="Échec export", status="warning", detail=str(exc)[:80]))
# #                 reply_parts.append(f"Impossible de générer l'export Excel : {exc}")
# #         else:
# #             steps.append(AgentStep(label="Aucun colis", status="warning"))
# #             reply_parts.append(
# #                 "Aucun colis trouvé pour cet export. Suivez d'abord un numéro dans le chat."
# #             )
# #             export_download = None
# #
# #     elif task == TASK_SUPPORT:
# #         tn = (answers.get("tracking_number") or "").strip() or extract_tracking_number(initial_message)
# #         issue = answers.get("issue_type") or "other"
# #         priority = answers.get("priority") or "medium"
# #         issue_labels = {
# #             "delay": "Retard de livraison",
# #             "damaged": "Colis endommagé",
# #             "lost": "Colis perdu",
# #             "wrong_address": "Mauvaise adresse",
# #             "other": "Autre problème",
# #         }
# #         subject = f"[Agent] {issue_labels.get(issue, 'Problème')} — {tn or 'sans numéro'}"
# #         body = initial_message.strip() or f"Signalement automatique via l'agent FedEx.\nType : {issue}."
# #         if tn:
# #             body += f"\nNuméro de suivi : {tn}"
# #             tracking_number = tn
# #             try:
# #                 data = fedex_service.get_shipment(tn)
# #                 body += f"\nStatut actuel : {data.get('status')} — {data.get('current_location')}"
# #             except Exception:
# #                 pass
# #
# #         steps.append(AgentStep(label="Création ticket support", status="running"))
# #         opened = open_client_support_ticket(
# #             db,
# #             user=user,
# #             message=body,
# #             tracking_number=tn or None,
# #             priority=priority,
# #         )
# #         ticket_number = opened["ticket_number"]
# #         steps.append(AgentStep(label="Ticket créé", status="done", detail=ticket_number))
# #         reply_parts.append(
# #             f"**Ticket support ouvert** — réf. `{ticket_number}`.\n"
# #             "Notre équipe a été notifiée. Vous pouvez suivre le dossier dans **Aide**."
# #         )
# #
# #     elif task == TASK_SUMMARY:
# #         scope = answers.get("scope") or "session"
# #         fmt = answers.get("format") or "text"
# #         send_mail = answers.get("send_email") == "yes"
# #         period = answers.get("period") or "week"
# #         limit_map = {"week": 7, "month": 30, "all": 365}
# #         days = limit_map.get(period, 7)
# #
# #         steps.append(AgentStep(label="Collecte des colis", status="running"))
# #         tns: list[str] = []
# #         if scope == "session":
# #             tns = session_tracking_numbers(db, session_id, user.id)
# #         else:
# #             from datetime import datetime, timedelta, timezone
# #
# #             since = datetime.now(timezone.utc) - timedelta(days=days)
# #             rows = list(
# #                 db.scalars(
# #                     select(TrackingRequest)
# #                     .where(TrackingRequest.user_id == user.id, TrackingRequest.created_at >= since)
# #                     .order_by(TrackingRequest.created_at.desc())
# #                     .limit(20)
# #                 ).all()
# #             )
# #             seen: set[str] = set()
# #             for r in rows:
# #                 if r.tracking_number not in seen:
# #                     seen.add(r.tracking_number)
# #                     tns.append(r.tracking_number)
# #
# #         tn_single = (answers.get("tracking_number") or "").strip() or extract_tracking_number(initial_message)
# #         if not tns and tn_single:
# #             tns = [tn_single]
# #
# #         steps.append(AgentStep(label="Interrogation FedEx", status="running", detail=f"{len(tns)} colis"))
# #         shipments_data: list[dict[str, Any]] = []
# #         lines = ["| Colis | Statut | Dernier événement | Heure |", "| --- | --- | --- | --- |"]
# #         for tn in tns[:5]:
# #             try:
# #                 data = fedex_service.get_shipment(tn)
# #                 upsert_shipment_cache(db, data)
# #                 shipments_data.append(data)
# #                 events = list(data.get("events") or [])
# #                 last_ev = events[0] if events else {}
# #                 when = str(last_ev.get("at") or "—")[:19].replace("T", " ")
# #                 lines.append(
# #                     f"| {tn} | {data.get('status') or '—'} | {last_ev.get('description') or '—'} | {when} |"
# #                 )
# #                 if not shipment_for_client:
# #                     tracking_number = tn
# #             except Exception as exc:
# #                 lines.append(f"| {tn} | Erreur FedEx | — | — |")
# #                 logger.warning("Résumé agent — FedEx %s : %s", tn, exc)
# #
# #         steps.append(AgentStep(label="Historique récupéré", status="done", detail=f"{len(shipments_data)} colis"))
# #
# #         if not shipments_data:
# #             reply_parts.append("Aucun colis trouvé pour générer le résumé. Suivez d'abord un numéro dans cette conversation.")
# #         else:
# #             summary_text = "\n".join(lines)
# #             if fmt == "pdf":
# #                 steps.append(AgentStep(label="Génération PDF", status="running"))
# #                 if len(shipments_data) == 1:
# #                     pdf_bytes = generate_shipment_history_pdf(shipments_data[0])
# #                     pdf_name = f"historique-{shipments_data[0]['tracking_number']}.pdf"
# #                 else:
# #                     pdf_bytes = generate_multi_shipment_history_pdf(shipments_data)
# #                     pdf_name = "historique-expeditions.pdf"
# #                 steps.append(AgentStep(label="PDF généré", status="done"))
# #
# #                 if send_mail and is_email_configured() and user.email:
# #                     steps.append(AgentStep(label="Envoi e-mail avec PDF", status="running"))
# #                     try:
# #                         send_email_with_attachment(
# #                             to=user.email,
# #                             subject="[Globex FedEx] Historique de suivi (PDF)",
# #                             body_text=(
# #                                 f"Bonjour {user.full_name or ''},\n\n"
# #                                 f"Veuillez trouver ci-joint le résumé horodaté de vos colis FedEx "
# #                                 f"({len(shipments_data)} colis).\n\n— Agent FedEx Globex"
# #                             ),
# #                             attachment_bytes=pdf_bytes,
# #                             attachment_filename=pdf_name,
# #                         )
# #                         steps.append(AgentStep(label="E-mail envoyé", status="done", detail=user.email))
# #                         create_user_notification(
# #                             db,
# #                             user_id=user.id,
# #                             type="document_ready",
# #                             title="Rapport PDF envoyé",
# #                             message=f"Historique FedEx envoyé à {user.email} ({len(shipments_data)} colis).",
# #                             related_tracking_number=shipments_data[0].get("tracking_number") or "",
# #                             link="/notifications",
# #                         )
# #                         reply_parts.append(
# #                             f"**Rapport PDF envoyé** à `{user.email}` — {len(shipments_data)} colis avec chronologie horodatée."
# #                         )
# #                     except Exception:
# #                         logger.exception("Échec envoi PDF résumé")
# #                         steps.append(AgentStep(label="Échec envoi e-mail", status="warning"))
# #                         reply_parts.append("Le PDF a été généré mais l'envoi e-mail a échoué. Vérifiez la configuration SMTP.")
# #                 else:
# #                     reply_parts.append(
# #                         f"**Rapport PDF généré** pour {len(shipments_data)} colis.\n"
# #                         "_Activez l'e-mail dans le questionnaire ou configurez SMTP pour l'envoi automatique._"
# #                     )
# #             else:
# #                 reply_parts.append(f"**Résumé de vos expéditions** :\n\n{summary_text}")
# #                 if send_mail and is_email_configured() and user.email:
# #                     steps.append(AgentStep(label="Envoi e-mail résumé", status="running"))
# #                     try:
# #                         send_email(
# #                             to=user.email,
# #                             subject="[Globex FedEx] Résumé de vos expéditions",
# #                             body_text=summary_text.replace("|", " ").replace("---", ""),
# #                         )
# #                         steps.append(AgentStep(label="E-mail envoyé", status="done"))
# #                         reply_parts.append(f"\nRésumé également envoyé à **{user.email}**.")
# #                     except Exception:
# #                         steps.append(AgentStep(label="Échec envoi e-mail", status="warning"))
# #
# #     elif task == TASK_POD:
# #         tn = (answers.get("tracking_number") or "").strip() or extract_tracking_number(initial_message)
# #         if not tn:
# #             tns = session_tracking_numbers(db, session_id, user.id)
# #             tn = tns[0] if tns else None
# #         if not tn:
# #             return _build_questionnaire_response(
# #                 flow_id=str(uuid.uuid4()),
# #                 task=task,
# #                 intro="Indiquez le numéro de suivi pour la preuve de livraison.",
# #                 questions=[
# #                     AgentQuestion(
# #                         id="tracking_number",
# #                         label="Numéro de suivi FedEx",
# #                         question_type="text",
# #                         options=[],
# #                     )
# #                 ],
# #             )
# #         tracking_number = tn
# #         send_mail = answers.get("send_email", "yes") == "yes"
# #         steps.append(AgentStep(label="Récupération preuve de livraison", status="running", detail=tn))
# #         try:
# #             from app.services.proof_of_delivery_service import get_proof_of_delivery_pdf
# #
# #             data = fedex_service.get_shipment(tn)
# #             pdf_bytes = get_proof_of_delivery_pdf(tn, shipment_data=data)
# #             steps.append(AgentStep(label="POD généré", status="done"))
# #             if send_mail and is_email_configured() and user.email:
# #                 send_email_with_attachment(
# #                     to=user.email,
# #                     subject=f"[Globex FedEx] Preuve de livraison — {tn}",
# #                     body_text=f"Bonjour {user.full_name or ''},\n\nPreuve de livraison FedEx pour le colis {tn}.\n\n— Agent FedEx Globex",
# #                     attachment_bytes=pdf_bytes,
# #                     attachment_filename=f"preuve-livraison-{tn}.pdf",
# #                 )
# #                 steps.append(AgentStep(label="POD envoyé par e-mail", status="done", detail=user.email))
# #                 reply_parts.append(f"**Preuve de livraison** envoyée à `{user.email}` pour le colis `{tn}`.")
# #             else:
# #                 reply_parts.append(f"**Preuve de livraison** générée pour `{tn}`. Consultez vos documents ou activez l'e-mail.")
# #         except Exception as exc:
# #             steps.append(AgentStep(label="POD indisponible", status="warning", detail=str(exc)[:80]))
# #             reply_parts.append(f"Impossible de générer la preuve de livraison pour `{tn}` : {exc}")
# #
# #     elif task == TASK_MULTI:
# #         scope = answers.get("multi_scope") or "session"
# #         if scope == "session":
# #             tns = session_tracking_numbers(db, session_id, user.id)
# #         else:
# #             rows = db.scalars(
# #                 select(TrackingRequest.tracking_number)
# #                 .where(TrackingRequest.user_id == user.id)
# #                 .order_by(TrackingRequest.created_at.desc())
# #                 .limit(5)
# #             ).all()
# #             tns = list(dict.fromkeys(rows))
# #         steps.append(AgentStep(label="Interrogation FedEx", status="running"))
# #         lines = ["| Colis | Statut | Livraison estimée |", "| --- | --- | --- |"]
# #         for tn in tns[:5]:
# #             try:
# #                 data = fedex_service.get_shipment(tn)
# #                 lines.append(f"| {tn} | {data.get('status') or '—'} | {data.get('estimated_delivery') or '—'} |")
# #                 if not shipment_for_client:
# #                     tracking_number = tn
# #             except Exception:
# #                 lines.append(f"| {tn} | Indisponible | — |")
# #         steps.append(AgentStep(label="Comparaison terminée", status="done"))
# #         reply_parts.append("**Comparaison multi-colis** :\n\n" + "\n".join(lines))
# #
# #     else:
# #         reply_parts.append("Tâche non reconnue. Choisissez une action dans le questionnaire.")
# #
# #     reply = "\n".join(reply_parts) if reply_parts else "Automatisation terminée."
# #     return {
# #         "reply": reply,
# #         "source": "agent",
# #         "intent": f"agent_{task}",
# #         "agent_mode": True,
# #         "agent_phase": "completed",
# #         "agent_questionnaire": None,
# #         "agent_steps": [s.model_dump() for s in steps],
# #         "shipment": shipment_for_client,
# #         "tracking_number": tracking_number,
# #         "export_download": export_download,
# #         "llm_provider": None,
# #     }
# # =============================================================================
# # ACTIVE — Phase 0 stub
# # =============================================================================
# """Agent client — stub Phase 0."""
#
# from __future__ import annotations
#
# from typing import Any
#
# from sqlalchemy.orm import Session
#
# from app.models.user import User
#
# TASK_PICKER = "task_picker"
# TASK_TRACK = "track_package"
#
#
# def should_route_to_client_agent(message: str) -> bool:
#     return False
#
#
# def open_client_support_ticket(
#     db: Session,
#     *,
#     user: User,
#     message: str,
#     tracking_number: str | None = None,
#     category: str = "delivery",
#     priority: str = "medium",
#     subject_prefix: str = "[Agent]",
# ) -> dict[str, Any]:
#     raise RuntimeError("Assistant en reconstruction")
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Agent client — stub Phase 0."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User

TASK_PICKER = "task_picker"
TASK_TRACK = "track_package"


def should_route_to_client_agent(message: str) -> bool:
    return False


def open_client_support_ticket(
    db: Session,
    *,
    user: User,
    message: str,
    tracking_number: str | None = None,
    category: str = "delivery",
    priority: str = "medium",
    subject_prefix: str = "[Agent]",
) -> dict[str, Any]:
    raise RuntimeError("Assistant en reconstruction")
