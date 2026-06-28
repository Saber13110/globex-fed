"""Détection intention surveillance colis — Phase 6."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from app.services.ai_assistant.export_normalize import parse_export_limit
from app.services.client_phase5.notification_filters import is_notification_workspace
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.shipment_watch_service import (
    ALERT_ALL,
    ALERT_DELAY,
    ALERT_DELIVERED,
    ALERT_OUT_FOR_DELIVERY,
)

EMAIL_LIMIT_CLARIFICATION_MARKER = "Combien de mails d'avancement"
TRACKING_CLARIFICATION_MARKER = "Quel numéro de suivi"
ALERT_AMBIGUOUS_MARKER = "Souhaitez-vous"

_LIVE_TRACKING_RE = re.compile(
    r"\b(ou est|ou se trouve|statut|localisation|position|suivi live|tracking status|where is)\b",
    re.I,
)
_WATCH_HINTS = (
    "surveill",
    "watch",
    "preven",
    "préven",
    "tiens-moi au courant",
    "tenez-moi au courant",
    "alerte mail",
    "alertes mail",
    "mail colis",
    "email colis",
    "courriel",
    "par mail",
    "par email",
    "envoie un mail",
    "envoie-moi un mail",
    "notifie par mail",
)
_STOP_HINTS = (
    "arrete",
    "arrête",
    "stop",
    "desactive",
    "désactive",
    "coupe",
    "plus d'alerte",
    "plus d alerte",
    "fin surveillance",
    "arret surveillance",
    "arrêt surveillance",
)
_UNLIMITED_RE = re.compile(
    r"\b(illimite|illimité|sans limite|autant que|a chaque changement|à chaque changement|"
    r"every update|unlimited|no limit)\b",
    re.I,
)
_EMAIL_LIMIT_FOLLOWUP_RE = re.compile(r"^\s*(\d{1,2})\s*$")
_APP_ONLY_RE = re.compile(r"\b(app|in-app|application|cloche)\b", re.I)
_EMAIL_CHANNEL_RE = re.compile(r"\b(mail|email|courriel|e-mail)\b", re.I)


def normalize_message_text(message: str) -> str:
    text = unicodedata.normalize("NFKD", (message or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def email_limit_clarification_message(lang: str) -> str:
    if lang == "en":
        return (
            "How many progress update emails would you like to receive for this shipment?\n"
            "Reply with a number (e.g. 3, 5) or « unlimited »."
        )
    return (
        f"{EMAIL_LIMIT_CLARIFICATION_MARKER} souhaitez-vous recevoir pour ce colis ?\n"
        "Répondez par un nombre (ex. 3, 5) ou « illimité »."
    )


def tracking_clarification_message(lang: str) -> str:
    if lang == "en":
        return f"{TRACKING_CLARIFICATION_MARKER} FedEx would you like to watch?"
    return f"{TRACKING_CLARIFICATION_MARKER} FedEx souhaitez-vous surveiller ?"


def alert_ambiguous_clarification_message(lang: str) -> str:
    if lang == "en":
        return (
            f"{ALERT_AMBIGUOUS_MARKER}:\n"
            "1. **View** past shipment alerts in your notification inbox\n"
            "2. **Activate** future email alerts for a shipment\n\n"
            "Reply with « view » or « activate »."
        )
    return (
        f"{ALERT_AMBIGUOUS_MARKER} :\n"
        "1. **Voir** vos alertes colis passées (notifications)\n"
        "2. **Activer** des alertes mail futures sur un colis\n\n"
        "Répondez par « voir » ou « activer »."
    )


def is_email_limit_clarification_followup(last_bot_message: str) -> bool:
    return EMAIL_LIMIT_CLARIFICATION_MARKER in (last_bot_message or "")


def is_tracking_clarification_followup(last_bot_message: str) -> bool:
    return TRACKING_CLARIFICATION_MARKER in (last_bot_message or "")


def is_alert_ambiguous_clarification_followup(last_bot_message: str) -> bool:
    return ALERT_AMBIGUOUS_MARKER in (last_bot_message or "")


def parse_email_limit_reply(message: str) -> int | None | Literal["invalid"]:
    text = normalize_message_text(message)
    if _UNLIMITED_RE.search(text):
        return None
    m = _EMAIL_LIMIT_FOLLOWUP_RE.match(text)
    if m:
        return min(max(int(m.group(1)), 1), 50)
    limit = parse_export_limit(message)
    if limit is not None:
        return limit
    if re.search(r"\b\d{1,2}\b", text):
        nums = [int(x) for x in re.findall(r"\b(\d{1,2})\b", text)]
        if nums:
            return min(max(nums[0], 1), 50)
    if text in {"illimite", "illimité", "unlimited", "infini"}:
        return None
    return "invalid"


def is_unlimited_email_message(message: str) -> bool:
    return bool(_UNLIMITED_RE.search(normalize_message_text(message)))


def parse_alert_ambiguous_reply(message: str) -> Literal["view", "activate"] | None:
    text = normalize_message_text(message)
    if any(w in text for w in ("voir", "view", "liste", "inbox", "passé", "passe")):
        return "view"
    if any(w in text for w in ("activer", "activate", "futur", "mail", "surveill", "alerte")):
        return "activate"
    return None


def extract_email_update_limit(message: str) -> int | None | Literal["missing"]:
    text = normalize_message_text(message)
    if _UNLIMITED_RE.search(text):
        return None
    m = re.search(r"\b(\d{1,2})\s*(fois|mails?|mises? a jour|updates?|alertes?)\b", text)
    if m:
        return min(max(int(m.group(1)), 1), 50)
    m_max = re.search(r"\b(?:max|limite)\s+(\d{1,2})\b", text)
    if m_max:
        return min(max(int(m_max.group(1)), 1), 50)
    limit = parse_export_limit(message)
    if limit is not None and any(k in text for k in ("mail", "email", "fois", "max", "limite")):
        return limit
    return "missing"


def resolve_notify_channels(message: str) -> tuple[bool, bool]:
    text = normalize_message_text(message)
    email = bool(_EMAIL_CHANNEL_RE.search(text))
    app_only = bool(_APP_ONLY_RE.search(text)) and not email
    if app_only:
        return False, True
    if email:
        return True, True
    return True, True


def detect_alert_type(message: str) -> str:
    text = normalize_message_text(message)
    if re.search(r"\b(livraison|livre|delivered)\b", text) and "exception" not in text:
        return ALERT_DELIVERED
    if re.search(r"\b(retard|delay|exception)\b", text):
        return ALERT_DELAY
    if re.search(r"\b(en livraison|out for delivery)\b", text):
        return ALERT_OUT_FOR_DELIVERY
    return ALERT_ALL


def is_stop_watch_message(message: str) -> bool:
    text = normalize_message_text(message)
    if not any(h in text for h in _STOP_HINTS):
        return False
    if any(k in text for k in ("colis", "surveill", "watch", "alerte", "mail", "tracking")):
        return True
    return bool(extract_tracking_number(message))


def is_watch_workspace(message: str) -> bool:
    from app.services.client_phase7.export_email_intent import (
        is_export_email_only_followup,
        wants_export_by_email,
    )

    if wants_export_by_email(message) or is_export_email_only_followup(message):
        return False
    try:
        from app.services.client_phase3.export_intent import is_excel_export_intent, is_pdf_export_intent

        if is_pdf_export_intent(message) or is_excel_export_intent(message):
            return False
    except ImportError:
        pass

    text = normalize_message_text(message)
    if not text:
        return False
    if is_stop_watch_message(message):
        return True
    if is_notification_workspace(message) and not any(h in text for h in _WATCH_HINTS):
        return False
    if _LIVE_TRACKING_RE.search(text) and not any(h in text for h in _WATCH_HINTS):
        return False
    if any(h in text for h in _WATCH_HINTS):
        return True
    if re.search(r"\b(alerte|alertes)\b", text) and re.search(
        r"\b(colis|tracking|shipment)\b", text
    ):
        return True
    return False


def detect_alert_ambiguous(message: str) -> bool:
    text = normalize_message_text(message)
    if any(h in text for h in _WATCH_HINTS):
        return False
    if _EMAIL_CHANNEL_RE.search(text):
        return False
    return bool(
        re.search(r"\b(alerte|alertes)\b", text)
        and re.search(r"\b(colis|tracking)\b", text)
        and not is_notification_workspace(message)
    )


def fallback_plan_from_message(message: str, *, lang: str) -> dict[str, Any] | None:
    if not is_watch_workspace(message):
        return None
    if is_stop_watch_message(message):
        return {
            "task_type": "stop_watch",
            "assistant_intro": "",
            "answers": {"tracking_number": extract_tracking_number(message) or ""},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }
    if detect_alert_ambiguous(message):
        return {
            "task_type": "activate_watch",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": alert_ambiguous_clarification_message(lang),
        }
    notify_email, notify_in_app = resolve_notify_channels(message)
    limit = extract_email_update_limit(message)
    tn = extract_tracking_number(message) or ""
    needs_tn = not tn
    needs_limit = notify_email and limit == "missing"
    if needs_tn:
        return {
            "task_type": "activate_watch",
            "assistant_intro": "",
            "answers": {
                "tracking_number": "",
                "alert_type": detect_alert_type(message),
                "notify_email": notify_email,
                "notify_in_app": notify_in_app,
                "max_email_updates": None if limit != "missing" else None,
            },
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": tracking_clarification_message(lang),
        }
    if needs_limit:
        return {
            "task_type": "activate_watch",
            "assistant_intro": "",
            "answers": {
                "tracking_number": tn,
                "alert_type": detect_alert_type(message),
                "notify_email": notify_email,
                "notify_in_app": notify_in_app,
            },
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": email_limit_clarification_message(lang),
        }
    max_updates = None if limit == "missing" else limit
    return {
        "task_type": "activate_watch",
        "assistant_intro": "Surveillance colis activée.",
        "answers": {
            "tracking_number": tn,
            "alert_type": detect_alert_type(message),
            "notify_email": notify_email,
            "notify_in_app": notify_in_app,
            "max_email_updates": max_updates,
        },
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }


def reconcile_watch_plan(message: str, plan: dict[str, Any], *, lang: str) -> dict[str, Any]:
    answers = dict(plan.get("answers") or {})
    tn = str(answers.get("tracking_number") or "").strip() or extract_tracking_number(message) or ""
    if tn:
        answers["tracking_number"] = tn
    if "alert_type" not in answers or not answers["alert_type"]:
        answers["alert_type"] = detect_alert_type(message)
    notify_email, notify_in_app = resolve_notify_channels(message)
    if "notify_email" not in answers:
        answers["notify_email"] = notify_email
    if "notify_in_app" not in answers:
        answers["notify_in_app"] = notify_in_app
    limit = extract_email_update_limit(message)
    if limit != "missing":
        answers["max_email_updates"] = limit
    elif answers.get("max_email_updates") == "":
        answers["max_email_updates"] = None
    plan["answers"] = answers
    if plan.get("task_type") == "activate_watch" and not plan.get("needs_clarification"):
        if not tn:
            plan["needs_clarification"] = True
            plan["ready_to_execute"] = False
            plan["clarification_question"] = tracking_clarification_message(lang)
        elif (
            answers.get("notify_email")
            and limit == "missing"
            and answers.get("max_email_updates") is None
            and not is_unlimited_email_message(message)
        ):
            plan["needs_clarification"] = True
            plan["ready_to_execute"] = False
            plan["clarification_question"] = email_limit_clarification_message(lang)
    return plan
