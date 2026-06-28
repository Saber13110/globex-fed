"""Détection intention rapport quotidien — Phase 8."""

from __future__ import annotations

import re
import unicodedata

from app.services.client_phase5.notification_filters import is_notification_workspace
from app.services.client_phase6.watch_intent import is_watch_workspace
from app.services.llm.tracking_extract import extract_tracking_number

SCHEDULE_TIME_CLARIFICATION_MARKER = "À quelle heure souhaitez-vous recevoir le rapport"

_DAILY_SIGNAL_RE = re.compile(
    r"\b("
    r"rapport du jour|rapport quotidien|rapport d activite|rapport d'activite|"
    r"bilan du jour|bilan activite|bilan aujourd|recap du jour|récap du jour|"
    r"activite aujourd|activité aujourd|daily report|what did i do today|"
    r"mon activite|mon activité|journal du jour|resume du jour|résumé du jour"
    r")\b",
    re.I,
)
_SEND_RE = re.compile(r"\b(envoie|envoyer|envoyez|mail|email|courriel|receive|get)\b", re.I)
_SCHEDULE_RE = re.compile(
    r"\b(chaque jour|tous les jours|every day|daily at|planif|programme|automatique|a \d|à \d)\b",
    re.I,
)
_DISABLE_RE = re.compile(
    r"\b(arrete|arrête|stop|desactive|désactive|annule|cancel)\b.*\b(rapport|report|quotidien|daily)\b|"
    r"\b(rapport|report)\b.*\b(arrete|arrête|stop|desactive|désactive)\b",
    re.I,
)
_EXPORT_COLIS_RE = re.compile(r"\b(pdf|excel|xlsx|export|document|fichier)\b", re.I)
_LIVE_TRACK_RE = re.compile(
    r"\b(ou est|où est|statut|localisation|where is|tracking status)\b",
    re.I,
)
_TIME_FOLLOWUP_RE = re.compile(r"^\s*(\d{1,2})[:hH\.](\d{2})?\s*$")


def normalize_message_text(message: str) -> str:
    text = unicodedata.normalize("NFKD", (message or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def is_daily_report_workspace(message: str) -> bool:
    text = normalize_message_text(message)
    if not text:
        return False
    if is_watch_workspace(message):
        return False
    if is_notification_workspace(message) and not _DAILY_SIGNAL_RE.search(text):
        return False
    tn = extract_tracking_number(message)
    if tn and _EXPORT_COLIS_RE.search(text) and not _DAILY_SIGNAL_RE.search(text):
        return False
    if tn and _LIVE_TRACK_RE.search(text) and not _DAILY_SIGNAL_RE.search(text):
        return False
    if _DAILY_SIGNAL_RE.search(text):
        return True
    if _DISABLE_RE.search(text):
        return True
    if _SCHEDULE_RE.search(text) and (_SEND_RE.search(text) or "rapport" in text or "report" in text):
        return True
    if _SEND_RE.search(text) and ("activite" in text or "activité" in text or "bilan" in text):
        return True
    return False


def is_schedule_time_clarification_followup(last_bot_message: str) -> bool:
    return SCHEDULE_TIME_CLARIFICATION_MARKER in (last_bot_message or "")


def parse_schedule_time_followup(message: str) -> str | None:
    from app.services.client_phase8.daily_report_preferences import parse_run_time

    text = normalize_message_text(message)
    if _TIME_FOLLOWUP_RE.match(text):
        return parse_run_time(message)
    return parse_run_time(message)


def schedule_time_clarification_message(lang: str) -> str:
    if lang == "en":
        return f"{SCHEDULE_TIME_CLARIFICATION_MARKER}? (e.g. 18:00)"
    return f"{SCHEDULE_TIME_CLARIFICATION_MARKER} ? (ex. 18:00)"


def fallback_plan_from_message(message: str, *, lang: str) -> dict | None:
    text = normalize_message_text(message)
    if _DISABLE_RE.search(text):
        return {
            "task_type": "disable_schedule",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }
    if _SCHEDULE_RE.search(text) or ("chaque jour" in text or "tous les jours" in text):
        from app.services.client_phase8.daily_report_preferences import parse_run_time

        rt = parse_run_time(message)
        if rt:
            return {
                "task_type": "configure_schedule",
                "assistant_intro": "",
                "answers": {"run_time": rt},
                "ready_to_execute": True,
                "needs_clarification": False,
                "clarification_question": "",
            }
        return {
            "task_type": "configure_schedule",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": False,
            "needs_clarification": True,
            "clarification_question": schedule_time_clarification_message(lang),
        }
    if _DAILY_SIGNAL_RE.search(text) or (_SEND_RE.search(text) and "rapport" in text):
        return {
            "task_type": "send_daily_report",
            "assistant_intro": "",
            "answers": {},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        }
    return None
