"""Filtres notifications — parité UI + reconcile sémantique."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from app.services.ai_assistant.export_normalize import parse_export_limit
from app.services.llm.tracking_extract import extract_tracking_number

CHAT_LIST_MAX = 50

_VALID_SECTIONS = frozenset({"all", "unread", "support", "tracking", "documents", "security", "ai"})
_VALID_MODES = frozenset({"list", "summarize", "export_pdf"})
_VALID_STATUS = frozenset({"all", "unread", "read"})
_VALID_PRIORITY = frozenset({"all", "high", "medium", "low"})

_SECTION_LABELS = {
    "fr": {
        "all": "toutes",
        "unread": "non lues",
        "support": "support",
        "tracking": "suivi colis",
        "documents": "documents",
        "security": "sécurité",
        "ai": "IA",
    },
    "en": {
        "all": "all",
        "unread": "unread",
        "support": "support",
        "tracking": "tracking",
        "documents": "documents",
        "security": "security",
        "ai": "AI",
    },
}


@dataclass
class NotificationQueryParams:
    mode: str = "list"
    section: str = "all"
    status: str = "all"
    tracking_number: str = ""
    search_query: str = ""
    semantic_topic: str = ""
    priority: str = "all"
    since_days: int | None = None
    limit: int = 15
    attach_pdf: bool = False


ReadIntent = Literal["list_read", "mark_all", "ambiguous"] | None

_READ_THEME_RE = re.compile(
    r"\b(deja lu|deja lues|deja lue|comme lu|comme lues|notifications? lues?|alertes? lues?|mark as read)\b",
    re.I,
)
_LIST_VERBS_RE = re.compile(
    r"\b(montre|montrez|liste|lister|affiche|affichez|donne|donnez|voir)\b",
    re.I,
)
_MARK_VERBS_RE = re.compile(
    r"\b(marque|marquer|rend|rendre|passer en lu|mettre en lu|tout lire|mark all)\b",
    re.I,
)
_AMBIGUOUS_READ_RE = re.compile(r"\bcomme deja lu\b|\bcomme lu\b", re.I)

_READ_CLARIFICATION_MARKER = "Souhaitez-vous"

_SECTION_KEYWORD_RES: dict[str, re.Pattern[str]] = {
    "support": re.compile(r"\b(support|ticket|admin)\b", re.I),
    "tracking": re.compile(r"\b(suivi colis|tracking|mise a jour colis|alertes? colis)\b", re.I),
    "documents": re.compile(r"\b(document|export ready|pod|preuve)\b", re.I),
    "security": re.compile(r"\b(securite|connexion|login)\b", re.I),
}


def read_clarification_message(lang: str) -> str:
    if lang == "en":
        return (
            "I'm not sure what you mean. Would you like to:\n"
            "1. **View** your already-read notifications\n"
            "2. **Mark all** your notifications as read\n\n"
            "Reply with « view » or « mark »."
        )
    return (
        "Je ne suis pas certain de votre demande. Souhaitez-vous :\n"
        "1. **Voir** vos notifications déjà lues\n"
        "2. **Marquer toutes** vos notifications comme lues\n\n"
        "Répondez par « voir » ou « marquer »."
    )


def detect_read_intent(message: str) -> ReadIntent:
    text = normalize_message_text(message)
    if not _READ_THEME_RE.search(text):
        return None
    if _LIST_VERBS_RE.search(text):
        return "list_read"
    if _AMBIGUOUS_READ_RE.search(text):
        return "ambiguous"
    if _MARK_VERBS_RE.search(text):
        return "mark_all"
    return "ambiguous"


def sanitize_phantom_filters(message: str, answers: dict[str, Any]) -> dict[str, Any]:
    text = normalize_message_text(message)
    section = str(answers.get("section") or "all").strip().lower()
    if section not in _SECTION_KEYWORD_RES:
        return answers
    pattern = _SECTION_KEYWORD_RES.get(section)
    if pattern and not pattern.search(text):
        answers["section"] = "all"

    mode = str(answers.get("mode") or "list").strip().lower()
    explicit_limit = extract_notification_limit(message)
    if explicit_limit is None:
        try:
            current_limit = int(answers.get("limit")) if answers.get("limit") is not None else None
        except (TypeError, ValueError):
            current_limit = None
        if current_limit == 1:
            answers["limit"] = default_limit_for_mode(mode)
    return answers


def build_read_clarification_plan(lang: str) -> dict[str, Any]:
    return {
        "task_type": "notifications_query",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": False,
        "needs_clarification": True,
        "clarification_question": read_clarification_message(lang),
    }


def build_mark_all_read_plan() -> dict[str, Any]:
    return {
        "task_type": "notifications_mark_all_read",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }


def build_list_read_plan(lang: str) -> dict[str, Any]:
    intro = (
        "Here are your already-read notifications."
        if lang == "en"
        else "Voici vos notifications déjà lues."
    )
    return {
        "task_type": "notifications_query",
        "assistant_intro": intro,
        "answers": {
            "mode": "list",
            "section": "all",
            "status": "read",
            "limit": default_limit_for_mode("list"),
        },
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }


def is_read_clarification_followup(last_bot_text: str) -> bool:
    return _READ_CLARIFICATION_MARKER in (last_bot_text or "")


def parse_read_clarification_reply(message: str) -> ReadIntent:
    text = normalize_message_text(message)
    if re.search(r"\b(voir|afficher|liste|lister|1)\b", text):
        return "list_read"
    if re.search(r"\b(marquer|marque|mark|2)\b", text):
        return "mark_all"
    return None


def apply_read_intent_to_plan(message: str, plan: dict[str, Any], *, lang: str) -> dict[str, Any]:
    if plan.get("needs_clarification"):
        return plan
    task = plan.get("task_type")
    if task == "notifications_mark_all_read":
        return plan
    intent = detect_read_intent(message)
    if intent == "ambiguous":
        return build_read_clarification_plan(lang)
    if intent == "mark_all" or task == "notifications_mark_all_read":
        return build_mark_all_read_plan()
    if intent == "list_read" and task == "notifications_query":
        answers = dict(plan.get("answers") or {})
        answers["status"] = "read"
        answers["section"] = "all"
        answers.setdefault("mode", "list")
        answers.setdefault("limit", default_limit_for_mode("list"))
        intro = plan.get("assistant_intro") or (
            "Here are your already-read notifications."
            if lang == "en"
            else "Voici vos notifications déjà lues."
        )
        return {**plan, "assistant_intro": intro, "answers": answers}
    return plan


def extract_notification_limit(message: str) -> int | None:
    """Extrait N depuis « 5 derniers », « juste les 3 alertes », etc."""
    return parse_export_limit(message, default=None)


def default_limit_for_mode(mode: str) -> int:
    m = (mode or "list").strip().lower()
    if m == "list":
        return 15
    return 30


def normalize_message_text(message: str) -> str:
    raw = (message or "").strip().lower()
    folded = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def section_to_api_type(section: str) -> str | None:
    sec = (section or "all").strip().lower()
    if sec == "unread":
        return None
    if sec == "support":
        return "support"
    if sec == "tracking":
        return "tracking_update"
    if sec == "documents":
        return "documents"
    if sec == "security":
        return "security_alert"
    if sec == "ai":
        return "ai_report"
    return None


def section_label(section: str, lang: str) -> str:
    labels = _SECTION_LABELS.get(lang, _SECTION_LABELS["fr"])
    return labels.get(section, section)


def params_from_answers(answers: dict[str, Any]) -> NotificationQueryParams:
    mode = str(answers.get("mode") or "list").strip().lower()
    if mode not in _VALID_MODES:
        mode = "list"
    section = str(answers.get("section") or "all").strip().lower()
    if section not in _VALID_SECTIONS:
        section = "all"
    status = str(answers.get("status") or "all").strip().lower()
    if status not in _VALID_STATUS:
        status = "all"
    priority = str(answers.get("priority") or "all").strip().lower()
    if priority not in _VALID_PRIORITY:
        priority = "all"
    since_raw = answers.get("since_days")
    since_days: int | None = None
    if since_raw is not None:
        try:
            since_days = int(since_raw)
        except (TypeError, ValueError):
            since_days = None
    limit_raw = answers.get("limit")
    if limit_raw is None:
        limit = default_limit_for_mode(mode)
    else:
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = default_limit_for_mode(mode)
    limit = min(max(limit, 1), CHAT_LIST_MAX)
    attach_pdf = bool(answers.get("attach_pdf"))
    if mode == "export_pdf":
        attach_pdf = True
    return NotificationQueryParams(
        mode=mode,
        section=section,
        status=status,
        tracking_number=str(answers.get("tracking_number") or "").strip(),
        search_query=str(answers.get("search_query") or "").strip(),
        semantic_topic=str(answers.get("semantic_topic") or "").strip(),
        priority=priority,
        since_days=since_days,
        limit=limit,
        attach_pdf=attach_pdf,
    )


def reconcile_notification_plan(message: str, plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("task_type") != "notifications_query":
        return plan
    answers = dict(plan.get("answers") or {})
    text = normalize_message_text(message)

    if re.search(r"\b(pdf|fichier|telecharger|telecharge|exporte|export)\b", text):
        answers["attach_pdf"] = True
        answers["mode"] = "export_pdf"

    if re.search(r"\b(resume|resumer|recap|synthese)\b", text) and not answers.get("attach_pdf"):
        answers["mode"] = "summarize"

    if re.search(r"\b(non lu|non lues|pas lu|unread)\b", text):
        answers["status"] = "unread"
        if answers.get("section") in (None, "", "all"):
            answers["section"] = "unread"

    if re.search(r"\b(deja lu|deja lues|deja lue|notifications? lues?|alertes? lues?)\b", text):
        answers["status"] = "read"
        if answers.get("section") in (None, "", "unread"):
            answers["section"] = "all"

    if re.search(r"\b(support|ticket|admin)\b", text):
        answers["section"] = "support"
    elif re.search(r"\b(suivi colis|tracking|mise a jour colis|alertes? colis)\b", text):
        answers["section"] = "tracking"
    elif re.search(r"\b(document|export ready|pod|preuve)\b", text):
        answers["section"] = "documents"
    elif re.search(r"\b(securite|connexion|login)\b", text):
        answers["section"] = "security"

    if re.search(r"\b(important|urgent|priorit)\b", text):
        answers["priority"] = "high"

    if re.search(r"\b(semaine|cette semaine|7 jours)\b", text):
        answers["since_days"] = 7
    elif re.search(r"\b(aujourd|today)\b", text):
        answers["since_days"] = 1

    tn = extract_tracking_number(message)
    if tn and not answers.get("tracking_number"):
        answers["tracking_number"] = tn

    topic = str(answers.get("semantic_topic") or "").strip()
    search = str(answers.get("search_query") or "").strip()
    if topic and not search:
        answers["search_query"] = topic

    if answers.get("section") == "unread" and answers.get("status") == "all":
        answers["status"] = "unread"

    mode = str(answers.get("mode") or "list").strip().lower()
    explicit_limit = extract_notification_limit(message)
    if explicit_limit is not None:
        answers["limit"] = explicit_limit
    else:
        limit_raw = answers.get("limit")
        try:
            current_limit = int(limit_raw) if limit_raw is not None else None
        except (TypeError, ValueError):
            current_limit = None
        if current_limit is None or current_limit == 30:
            answers["limit"] = default_limit_for_mode(mode)

    answers = sanitize_phantom_filters(message, answers)
    return {**plan, "answers": answers}


def fallback_plan_from_message(message: str, *, lang: str = "fr") -> dict[str, Any] | None:
    text = normalize_message_text(message)
    if not is_notification_workspace(message):
        return None
    read_intent = detect_read_intent(message)
    if read_intent == "ambiguous":
        return build_read_clarification_plan(lang)
    if read_intent == "mark_all":
        return build_mark_all_read_plan()
    mode = "list"
    if re.search(r"\b(resume|resumer|recap|synthese)\b", text):
        mode = "summarize"
    if re.search(r"\b(pdf|fichier|telecharger|exporte)\b", text):
        mode = "export_pdf"
    explicit_limit = extract_notification_limit(message)
    answers: dict[str, Any] = {
        "mode": mode,
        "section": "all",
        "status": "all",
        "limit": explicit_limit if explicit_limit is not None else default_limit_for_mode(mode),
    }
    if mode == "export_pdf":
        answers["attach_pdf"] = True
    plan = reconcile_notification_plan(message, {"task_type": "notifications_query", "answers": answers})
    result = {
        "task_type": "notifications_query",
        "assistant_intro": "",
        "answers": plan["answers"],
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    return apply_read_intent_to_plan(message, result, lang=lang)


_LIVE_TRACKING_RE = re.compile(
    r"\b(ou est|ou se trouve|statut|localisation|livraison)\b.*\b(colis|tracking)\b",
    re.I,
)
_CONVERSATION_RE = re.compile(
    r"\b(conversations?|discussions?|chats?|echange)\b",
    re.I,
)


def is_notification_workspace(message: str) -> bool:
    text = normalize_message_text(message)
    if not text:
        return False
    if _CONVERSATION_RE.search(text) and not re.search(
        r"\b(notification|alerte|notif|cloche)\b", text
    ):
        return False
    if _LIVE_TRACKING_RE.search(text) and not re.search(
        r"\b(notification|alerte|notif)\b", text
    ):
        return False
    hints = (
        "notification",
        "notifications",
        "notif",
        "alerte",
        "alertes",
        "cloche",
        "non lu",
        "pas lu",
        "deja lu",
        "deja lues",
        "unread",
        "message support",
        "reponse admin",
    )
    return any(h in text for h in hints)
