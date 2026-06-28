"""Détection intention ticket support — Phase 11."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.services.client_phase5.notification_filters import is_notification_workspace
from app.services.client_phase6.watch_intent import is_watch_workspace
from app.services.client_phase8.daily_report_intent import is_daily_report_workspace
from app.services.client_phase11.router_prompt import (
    TICKET_CONFIRMATION_MARKER,
    TRACKING_CLARIFICATION_MARKER,
)
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

_SUPPORT_SIGNAL_RE = re.compile(
    r"\b("
    r"ticket|support|r[eé]clamation|plainte|plaite|signaler|contacter l.?admin|"
    r"contacte[rz]? l.?admin|envoyer? (?:a |à )?l.?admin|demande support|"
    r"ouvrir un ticket|open a ticket|helpdesk|escalade|probl[eè]me avec|"
    r"colis endommag|colis perdu|colis bloqu|colis est bloqu|"
    r"bloqu[eé] en douane|douane|ne re[cç]ois pas|pas re[cç]u"
    r")\b",
    re.I,
)
_LIVE_TRACK_RE = re.compile(
    r"\b(ou est|o[uù] est|statut|localisation|where is|tracking status)\b",
    re.I,
)
_DOC_WORKSPACE_RE = re.compile(
    r"\b("
    r"documents?|fichiers?|exports?|preuves?|rapports?|"
    r"mes fichiers|mes documents|page documents|biblioth[eè]que|"
    r"t[eé]l[eé]charge|download"
    r")\b",
    re.I,
)
_CONV_RE = re.compile(r"\b(conversations?|discussions?|chats?)\b", re.I)
_LIST_TICKETS_RE = re.compile(
    r"\b(liste|lister|montre|voir|mes)\s+(mes\s+)?tickets?\b|"
    r"\bmy\s+support\s+tickets?\b",
    re.I,
)
_CONFIRM_RE = re.compile(
    r"^\s*(oui|yes|ok|d'accord|daccord|envoie|envoyer|envoyez|confirme|confirmer|"
    r"valide|valider|go|send|confirm)\b",
    re.I,
)
_CANCEL_RE = re.compile(
    r"^\s*(non|no|annule|annuler|cancel|stop|pas maintenant)\b",
    re.I,
)
_EXPLICIT_SEND_RE = re.compile(
    r"\b(envoie|envoyer|envoyez|ouvre|ouvrir|cr[eé]e|cr[eé]er)\b.*\b(ticket|support)\b|"
    r"\b(ticket|support)\b.*\b(maintenant|tout de suite|right now)\b",
    re.I,
)


def normalize_message_text(message: str) -> str:
    text = unicodedata.normalize("NFKD", (message or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def _is_document_library_workspace(message: str) -> bool:
    if _DOC_WORKSPACE_RE.search(message or ""):
        return True
    if _CONV_RE.search(message or "") and not _SUPPORT_SIGNAL_RE.search(message or ""):
        return False
    return False


def is_support_workspace(message: str) -> bool:
    text = normalize_message_text(message)
    if not text:
        return False
    if is_daily_report_workspace(message):
        return False
    if _is_document_library_workspace(message):
        return False
    if is_notification_workspace(message) and not _SUPPORT_SIGNAL_RE.search(message or ""):
        return False
    if is_watch_workspace(message) and not _SUPPORT_SIGNAL_RE.search(message or ""):
        return False
    tn = extract_tracking_number(message or "")
    if tn and is_plausible_tracking_number(tn) and _LIVE_TRACK_RE.search(message or ""):
        if not _SUPPORT_SIGNAL_RE.search(message or ""):
            return False
    if _LIST_TICKETS_RE.search(message or ""):
        return True
    return bool(_SUPPORT_SIGNAL_RE.search(message or ""))


def is_ticket_confirmation_followup(last_bot_message: str) -> bool:
    return TICKET_CONFIRMATION_MARKER in (last_bot_message or "")


def is_tracking_clarification_followup(last_bot_message: str) -> bool:
    return TRACKING_CLARIFICATION_MARKER in (last_bot_message or "")


def is_user_confirmation(message: str) -> bool:
    return bool(_CONFIRM_RE.search((message or "").strip()))


def is_user_cancellation(message: str) -> bool:
    return bool(_CANCEL_RE.search((message or "").strip()))


def tracking_clarification_message(lang: str) -> str:
    if lang == "en":
        return f"{TRACKING_CLARIFICATION_MARKER} for this shipment?"
    return f"{TRACKING_CLARIFICATION_MARKER} concerné ?"


def ticket_confirmation_message(
    *,
    subject: str,
    message: str,
    category: str,
    priority: str,
    tracking_number: str | None,
    lang: str,
) -> str:
    tn_line = f"\n- Tracking: `{tracking_number}`" if tracking_number else ""
    if lang == "en":
        return (
            f"**Support ticket draft**\n\n"
            f"- Subject: {subject}\n"
            f"- Category: {category}\n"
            f"- Priority: {priority}{tn_line}\n\n"
            f"{message[:800]}\n\n"
            f"{TICKET_CONFIRMATION_MARKER} to the admin team? Reply **yes** or **send**."
        )
    return (
        f"**Brouillon de ticket support**\n\n"
        f"- Sujet : {subject}\n"
        f"- Catégorie : {category}\n"
        f"- Priorité : {priority}{tn_line}\n\n"
        f"{message[:800]}\n\n"
        f"{TICKET_CONFIRMATION_MARKER} à l'équipe admin ? Répondez **oui** ou **envoie**."
    )


def list_my_tickets_message(lang: str) -> str:
    if lang == "en":
        return (
            "You can view and follow your support tickets in **Help → My tickets** "
            "or at `/support`."
        )
    return (
        "Consultez et suivez vos tickets dans **Aide → Mes tickets** "
        "ou sur la page `/support`."
    )


def fallback_plan_from_message(message: str, *, lang: str) -> dict[str, Any] | None:
    del lang
    if not is_support_workspace(message):
        return None
    text = normalize_message_text(message)
    if _LIST_TICKETS_RE.search(message or "") and not _SUPPORT_SIGNAL_RE.search(message or ""):
        return {
            "task_type": "list_my_tickets",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }
    tn = extract_tracking_number(message or "")
    subject = "Demande client via chat"
    if "endommag" in text or "damaged" in text:
        subject = "Colis endommagé"
    elif "perdu" in text or "lost" in text:
        subject = "Colis perdu"
    elif any(k in text for k in ("mail", "email", "courriel")):
        subject = "Problème e-mails de suivi"
    elif "retard" in text or "delay" in text:
        subject = "Retard de livraison"
    elif "douane" in text or "customs" in text:
        subject = "Blocage douane"
    priority = "high" if any(k in text for k in ("urgent", "endommag", "perdu", "lost")) else "medium"
    category = "tracking" if tn or any(k in text for k in ("colis", "livraison", "delivery")) else "other"
    needs_tn = category == "tracking" and not tn
    ready = bool(_EXPLICIT_SEND_RE.search(message or "")) and not needs_tn
    return {
        "task_type": "open_support_ticket",
        "assistant_intro": "",
        "answers": {
            "subject": subject,
            "message": (message or "").strip() or "Signalement via le chat client FedEx.",
            "category": category,
            "priority": priority,
            "tracking_number": tn or "",
        },
        "ready_to_execute": ready,
        "needs_clarification": needs_tn,
        "clarification_question": tracking_clarification_message("fr") if needs_tn else "",
    }
