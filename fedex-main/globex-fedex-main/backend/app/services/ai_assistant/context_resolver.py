"""Résolveur de contexte central — références, sujets, limites export."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.entity_memory import (
    EntityMemory,
    is_contextual_reference,
    is_tracking_follow_up,
)
from app.services.ai_assistant.export_normalize import parse_export_limit
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

SubjectType = Literal["tracking", "users", "notifications", "tickets", "security", "reports", "logs", "generic"]
FollowUpKind = Literal[
    "none", "location", "creator", "delay", "status", "history_export", "profile", "role", "email", "duration",
]

_WHERE_RE = re.compile(r"\b(o[uù]\s+est|where\s+is|actuellement|maintenant)\b", re.I)
_CREATOR_RE = re.compile(
    r"\b(qui a cr[eé][eé]|qui l.?a cr[eé][eé]|who created|cr[eé]ateur|created by|qui a initi[eé])\b",
    re.I,
)
_TRACKING_REF_RE = re.compile(r"\b(ce suivi|ce colis|this package|that package)\b", re.I)
_DELAY_RE = re.compile(
    r"\b(retard|delayed|anomalie|delay|livraison pr[eé]vue|estimated delivery)\b",
    re.I,
)
_ROLE_RE = re.compile(r"\b(r[oô]le|role)\b", re.I)
_EMAIL_RE = re.compile(r"\b(email|e-mail|mail|courriel)\b", re.I)
_DURATION_RE = re.compile(
    r"\b(depuis combien|combien de temps|how long|dans cet [eé]tat|depuis quand)\b",
    re.I,
)
_PROFILE_EXPORT_RE = re.compile(
    r"\b(son profil|uniquement son profil|exporte.?son profil|exporte le profil|this profile)\b",
    re.I,
)
_ORDINAL_RE = re.compile(
    r"\b(premier|première|deuxième|deuxieme|troisième|troisieme|\d+(?:e|er|ème|eme)?)\b",
    re.I,
)
_ORDINAL_USER_RE = re.compile(
    r"\b((?:premier|deuxi[eè]me|troisi[eè]me|\d+(?:e|er|ème|eme)?)\s+utilisateur)\b",
    re.I,
)
_EXPORT_HISTORY_RE = re.compile(
    r"\b(son historique|historique du colis|exporte.?le|exporte le|exporte son historique)\b",
    re.I,
)
_EXPORT_RE = re.compile(r"\b(export|exporte|pdf|xlsx|t[eé]l[eé]charge)\b", re.I)


@dataclass
class ResolvedContext:
    """Contexte résolu pour un tour de conversation."""

    original_message: str
    resolved_message: str
    language: str = "fr"
    subject_type: SubjectType = "generic"
    subject_id: str | None = None
    tracking_number: str | None = None
    export_limit: int | None = None
    follow_up_kind: FollowUpKind = "none"
    is_contextual: bool = False
    is_export: bool = False
    use_memory_only: bool = False
    ordinal_index: int | None = None
    hints: list[str] = field(default_factory=list)


def _ordinal_to_index(text: str) -> int | None:
    m = _ORDINAL_USER_RE.search(text)
    if m:
        word = m.group(1).lower()
        mapping = {"premier": 0, "première": 0, "deuxième": 1, "deuxieme": 1, "troisième": 2, "troisieme": 2}
        for k, v in mapping.items():
            if k in word:
                return v
        dm = re.search(r"(\d+)", word)
        if dm:
            return max(0, int(dm.group(1)) - 1)
    if re.search(r"\bdeuxi[eè]me\b", text, re.I):
        return 1
    if re.search(r"\btroisi[eè]me\b", text, re.I):
        return 2
    if re.search(r"\bpremier\b|\bpremière\b", text, re.I):
        return 0
    dm = re.search(r"\b(\d+)\s*(?:e|er|ème|eme|premiers?|derniers?)\b", text, re.I)
    if dm:
        return max(0, int(dm.group(1)) - 1)
    return None


def resolve_context(
    message: str,
    *,
    conv: ConversationState,
    memory: EntityMemory | None = None,
    language: str = "fr",
) -> ResolvedContext:
    """
    Résout références implicites : il, son, ce colis, les 3 premiers, etc.
    """
    text = (message or "").strip()
    mem = memory or EntityMemory.from_copilot_state(conv.merge_into_copilot_state({}))
    ctx = ResolvedContext(original_message=text, resolved_message=text, language=language)

    # Sync mémoire legacy → conversation_state
    if mem.last_tracking_number and not conv.last_tracking_number:
        conv.last_tracking_number = mem.last_tracking_number
    if mem.last_module == "users" and not conv.last_users_result and mem.last_export_dataset:
        conv.last_user_list = list(mem.last_export_dataset)[:50]
        conv.last_exportable_result = {"type": "users", "data": conv.last_user_list}

    tn = extract_tracking_number(text)
    if tn:
        ctx.tracking_number = tn
        ctx.subject_type = "tracking"
        ctx.subject_id = tn
        if _EXPORT_RE.search(text):
            ctx.is_export = True
            ctx.follow_up_kind = "history_export"
        return ctx

    contextual = is_contextual_reference(text)
    ctx.is_contextual = contextual
    ctx.export_limit = parse_export_limit(text)

    # --- Tracking context ---
    tracking_ctx = (
        conv.last_tracking_number
        and (
            is_tracking_follow_up(text, mem)
            or contextual
            or _EXPORT_HISTORY_RE.search(text)
            or _CREATOR_RE.search(text)
            or _DELAY_RE.search(text)
            or _TRACKING_REF_RE.search(text)
        )
    )
    if tracking_ctx:
        ctx.tracking_number = conv.last_tracking_number
        ctx.subject_type = "tracking"
        ctx.subject_id = conv.last_tracking_number

        if _CREATOR_RE.search(text):
            ctx.follow_up_kind = "creator"
            ctx.use_memory_only = bool(conv.last_tracking_result)
        elif _DELAY_RE.search(text):
            ctx.follow_up_kind = "delay"
            ctx.use_memory_only = bool(conv.last_tracking_result)
        elif _DURATION_RE.search(text):
            ctx.follow_up_kind = "duration"
            ctx.use_memory_only = bool(conv.last_tracking_result)
        elif _WHERE_RE.search(text) or re.search(r"\b(il|elle)\b", text, re.I):
            ctx.follow_up_kind = "location"
        elif _EXPORT_HISTORY_RE.search(text) or (_EXPORT_RE.search(text) and contextual):
            ctx.is_export = True
            ctx.follow_up_kind = "history_export"
        else:
            ctx.follow_up_kind = "status"

        ctx.resolved_message = f"[colis {ctx.tracking_number}] {text}"
        ctx.hints.append(f"tracking:{ctx.tracking_number}")
        logger.info("[ContextResolver] tracking follow-up kind=%s tn=%s", ctx.follow_up_kind, ctx.tracking_number)
        return ctx

    # --- Users context ---
    export_ds = conv.last_exportable_result or conv.last_exportable_dataset
    users = conv.get_users_list()
    users_ctx = bool(users) or conv.last_users_result or (export_ds and export_ds.get("type") == "users")
    if users_ctx and (
        contextual
        or _ROLE_RE.search(text)
        or _EMAIL_RE.search(text)
        or _ORDINAL_USER_RE.search(text)
        or _ORDINAL_RE.search(text)
        or _PROFILE_EXPORT_RE.search(text)
        or (ctx.export_limit and _EXPORT_RE.search(text))
        or (_EXPORT_RE.search(text) and re.search(r"\b(son|lui|le|la)\b", text, re.I))
    ):
        ctx.subject_type = "users"
        if not users and export_ds:
            users = (export_ds or {}).get("data") or []
        idx = _ordinal_to_index(text)
        if idx is not None and users and idx < len(users):
            ctx.ordinal_index = idx
            u = users[idx]
            ctx.subject_id = str(u.get("id") or u.get("email") or "")
            conv.last_selected_user = u
        elif conv.last_selected_user and (_PROFILE_EXPORT_RE.search(text) or contextual):
            ctx.ordinal_index = None
            ctx.subject_id = str(conv.last_selected_user.get("id") or conv.last_selected_user.get("email") or "")

        if _PROFILE_EXPORT_RE.search(text) or (_EXPORT_RE.search(text) and re.search(r"\bson profil\b", text, re.I)):
            ctx.follow_up_kind = "profile"
            ctx.is_export = True
        elif _ROLE_RE.search(text):
            ctx.follow_up_kind = "role"
            if ctx.ordinal_index is None:
                ctx.ordinal_index = idx if idx is not None else (1 if re.search(r"\bdeuxi", text, re.I) else 0)
        elif _EMAIL_RE.search(text):
            ctx.follow_up_kind = "email"
            if ctx.ordinal_index is None:
                ctx.ordinal_index = idx if idx is not None else 0
        elif _EXPORT_RE.search(text):
            ctx.is_export = True
        ctx.resolved_message = f"[utilisateurs en mémoire: {len(users)}] {text}"
        ctx.hints.append("users:context")
        return ctx

    # --- Notifications context ---
    if contextual and (conv.last_notifications_result or (export_ds and export_ds.get("type") == "notifications")):
        ctx.subject_type = "notifications"
        if _EXPORT_RE.search(text):
            ctx.is_export = True
        ctx.resolved_message = f"[notifications en mémoire] {text}"
        ctx.hints.append("notifications:context")
        return ctx

    # --- Generic export with limit ---
    if _EXPORT_RE.search(text) and contextual and export_ds:
        ctx.is_export = True
        ctx.subject_type = export_ds.get("type", "generic")  # type: ignore
        ctx.resolved_message = f"[export {ctx.subject_type} limit={ctx.export_limit}] {text}"
        return ctx

    # Subject type from conversation state
    if conv.last_tracking_number:
        ctx.hints.append(f"last_tracking:{conv.last_tracking_number}")
    if conv.last_subject_type:
        ctx.subject_type = conv.last_subject_type  # type: ignore

    return ctx


def update_subject_from_tool(conv: ConversationState, tool_name: str, payload: dict[str, Any]) -> None:
    """Met à jour last_subject_type/id après exécution outil."""
    if payload.get("status") == "error":
        return
    if "tracking" in tool_name or payload.get("tracking_number"):
        conv.last_subject_type = "tracking"
        conv.last_subject_id = str(payload.get("tracking_number") or conv.last_tracking_number or "")
    elif "user" in tool_name:
        conv.last_subject_type = "users"
        users = payload.get("users") or []
        if users and isinstance(users[0], dict):
            conv.last_subject_id = str(users[0].get("id") or "")
    elif "notification" in tool_name:
        conv.last_subject_type = "notifications"
    elif "ticket" in tool_name:
        conv.last_subject_type = "tickets"
    elif "security" in tool_name:
        conv.last_subject_type = "security"
    elif "report" in tool_name or "platform" in tool_name:
        conv.last_subject_type = "reports"
