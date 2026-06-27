"""Mémoire entités — session + résolution références (il, ce colis, ces notifications…)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"et maintenant|maintenant|o[uù]\s+est|o[uù]\s+est.?il|where\s+is|"
    r"et lui|et elle|et ce|et celui|et celle|"
    r"montre.?moi|show me|d[eé]tails?|details?|"
    r"pourquoi|why|comment|how come|"
    r"celui.?ci|celle.?ci|ce colis|this package|that package|"
    r"cet utilisateur|this user|that user|"
    r"ce ticket|this ticket|"
    r"ce rapport|this report|"
    r"son statut|quel est son|qui est l.?exp[eé]diteur|exp[eé]diteur|"
    r"exporte.?le|exporte le|g[eé]n[eè]re.?un pdf|son historique|"
    r"^il\b|^elle\b|^le\b|^la\b"
    r")\b",
    re.I,
)

_TRACKING_FOLLOWUP_RE = re.compile(
    r"\b("
    r"o[uù]\s+est|where\s+is|statut|status|exp[eé]diteur|shipper|sender|"
    r"exporte.?le|exporte le|son historique|maintenant|il\b|elle\b"
    r")\b",
    re.I,
)

_CONTEXTUAL_REFERENCE_RE = re.compile(
    r"\b("
    r"il\b|elle\b|lui\b|"
    r"ça\b|ca\b|ceci\b|cela\b|"
    r"ce\s+colis|ce\s+ticket|cet\s+utilisateur|ce\s+rapport|"
    r"cette\s+analyse|cette\s+liste|"
    r"ces\s+(notifs?|notifications?|logs?|utilisateurs?|tickets?|colis|rapports?)|"
    r"celles.?ci|ceux.?ci|celles.?là|ceux.?là|"
    r"exporte.?les|fournis.?les|g[eé]n[eè]re.?les|"
    r"mets.?les|met.?les|t[eé]l[eé]charge.?les|"
    r"exporte.?ça|exporte.?ca|fournis.?ça|fournis.?ca|"
    r"exporte.?ce|exporte.?cette|g[eé]n[eè]re.?un\s+pdf\s+de\s+cette"
    r")\b",
    re.I,
)

_PRONOUN_TRACKING_RE = re.compile(
    r"\b(il|elle|le colis|la commande|this one|that one|it)\b",
    re.I,
)
_PRONOUN_USER_RE = re.compile(
    r"\b(lui|elle|cet utilisateur|this user|that user|him|her)\b",
    re.I,
)
_PRONOUN_TICKET_RE = re.compile(
    r"\b(ce ticket|this ticket|that ticket|le ticket)\b",
    re.I,
)
_PRONOUN_NOTIFICATIONS_RE = re.compile(
    r"\b(ces\s+notifs?|ces\s+notifications?|celles.?ci|exporte.?les|fournis.?les)\b",
    re.I,
)


@dataclass
class EntityMemory:
    """Entités actives mémorisées en session."""

    last_tracking_number: str | None = None
    last_user_id: int | None = None
    last_user_email: str | None = None
    last_ticket_id: int | None = None
    last_incident_id: int | None = None
    last_report_module: str | None = None
    last_module: str | None = None
    last_intent: str | None = None
    last_result_summary: str | None = None
    last_limit: int | None = None
    last_query_type: str | None = None
    tracking_numbers: list[str] = field(default_factory=list)
    user_ids: list[int] = field(default_factory=list)
    last_notifications: list[dict[str, Any]] = field(default_factory=list)
    last_logs: list[dict[str, Any]] = field(default_factory=list)
    last_ticket_items: list[dict[str, Any]] = field(default_factory=list)
    last_export_dataset: list[dict[str, Any]] = field(default_factory=list)
    last_security_incident: dict[str, Any] | None = None
    last_payload: dict[str, Any] | None = None

    @classmethod
    def from_copilot_state(cls, state: dict[str, Any] | None) -> EntityMemory:
        if not state:
            return cls()
        tracking_list = list(state.get("last_tracking_numbers") or [])
        user_list = list(state.get("last_user_ids") or [])
        entity = cls(
            last_tracking_number=state.get("last_tracking_number") or (tracking_list[0] if tracking_list else None),
            last_user_id=state.get("last_user_id") or (user_list[0] if user_list else None),
            last_user_email=state.get("last_user_email"),
            last_ticket_id=state.get("last_ticket_id"),
            last_incident_id=state.get("last_incident_id"),
            last_report_module=state.get("last_report_module"),
            last_module=state.get("last_module"),
            last_intent=state.get("last_intent"),
            last_result_summary=state.get("last_result_summary"),
            last_limit=state.get("last_limit"),
            last_query_type=state.get("last_query_type"),
            tracking_numbers=tracking_list[:20],
            user_ids=user_list[:20],
            last_notifications=list(state.get("last_notifications") or state.get("last_items") or [])[:50],
            last_logs=list(state.get("last_logs") or [])[:50],
            last_ticket_items=list(state.get("last_ticket_items") or [])[:50],
            last_export_dataset=list(state.get("last_export_dataset") or state.get("last_items") or [])[:50],
            last_security_incident=state.get("last_security_incident"),
            last_payload=state.get("last_payload"),
        )
        if state.get("last_module") == "notifications" and state.get("last_items"):
            entity.last_notifications = list(state["last_items"])[:50]
        export_ds = state.get("last_exportable_dataset")
        if isinstance(export_ds, dict) and export_ds.get("data"):
            entity.last_export_dataset = list(export_ds["data"])[:50]
            entity.last_module = export_ds.get("type") or entity.last_module
        return entity

    def to_state_updates(self) -> dict[str, Any]:
        updates = {
            "last_tracking_number": self.last_tracking_number,
            "last_tracking_numbers": self.tracking_numbers[:20],
            "last_user_id": self.last_user_id,
            "last_user_ids": self.user_ids[:20],
            "last_user_email": self.last_user_email,
            "last_ticket_id": self.last_ticket_id,
            "last_incident_id": self.last_incident_id,
            "last_report_module": self.last_report_module,
            "last_module": self.last_module,
            "last_intent": self.last_intent,
            "last_result_summary": self.last_result_summary,
            "last_limit": self.last_limit,
            "last_query_type": self.last_query_type,
            "last_notifications": self.last_notifications[:50],
            "last_logs": self.last_logs[:50],
            "last_ticket_items": self.last_ticket_items[:50],
            "last_export_dataset": self.last_export_dataset[:50],
            "last_security_incident": self.last_security_incident,
            "last_payload": self.last_payload,
        }
        if self.last_export_dataset and self.last_module:
            updates["last_exportable_dataset"] = {
                "type": self.last_module,
                "data": self.last_export_dataset[:50],
            }
        return updates

    def has_exportable_context(self) -> bool:
        return bool(
            self.last_notifications
            or self.last_export_dataset
            or self.last_logs
            or self.last_ticket_items
            or (self.last_payload and self.last_module)
        )

    def update_from_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        intent: str | None = None,
        query_type: str | None = None,
        limit: int | None = None,
    ) -> None:
        """Met à jour les entités depuis le résultat d'un outil."""
        if intent:
            self.last_intent = intent
        if query_type:
            self.last_query_type = query_type
        if limit:
            self.last_limit = limit

        self.last_payload = {k: v for k, v in payload.items() if k != "status"}

        tn = payload.get("tracking_number")
        if tn:
            self.last_tracking_number = str(tn)
            if str(tn) not in self.tracking_numbers:
                self.tracking_numbers.insert(0, str(tn))
            self.last_module = "tracking"

        uid = payload.get("user_id")
        if uid is not None:
            try:
                self.last_user_id = int(uid)
                if self.last_user_id not in self.user_ids:
                    self.user_ids.insert(0, self.last_user_id)
            except (TypeError, ValueError):
                pass
        email = payload.get("user_email")
        if email:
            self.last_user_email = str(email)

        users = payload.get("users") or payload.get("admin_accounts") or []
        if users:
            self.last_export_dataset = [u for u in users if isinstance(u, dict)][:50]

        for u in users:
            if isinstance(u, dict) and u.get("id"):
                try:
                    uid = int(u["id"])
                    self.last_user_id = uid
                    if uid not in self.user_ids:
                        self.user_ids.insert(0, uid)
                    if u.get("email"):
                        self.last_user_email = str(u["email"])
                except (TypeError, ValueError):
                    pass

        sample = payload.get("sample") or []
        if isinstance(sample, list) and sample:
            if "notification" in tool_name:
                self.last_notifications = [x for x in sample if isinstance(x, dict)][:50]
                self.last_export_dataset = self.last_notifications
                self.last_module = "notifications"
            elif "log" in tool_name:
                self.last_logs = [x for x in sample if isinstance(x, dict)][:50]
                self.last_export_dataset = self.last_logs
                self.last_module = "logs"
            elif "tracking" in tool_name:
                self.last_export_dataset = [x for x in sample if isinstance(x, dict)][:50]
                self.last_module = "tracking"

        for t in payload.get("tickets") or []:
            if isinstance(t, dict) and t.get("id") and "subject" in t:
                try:
                    self.last_ticket_id = int(t["id"])
                    self.last_module = "tickets"
                except (TypeError, ValueError):
                    pass
        tickets = payload.get("tickets") or []
        if tickets:
            self.last_ticket_items = [t for t in tickets if isinstance(t, dict)][:50]
            self.last_export_dataset = self.last_ticket_items

        for inc in payload.get("incidents") or []:
            if isinstance(inc, dict) and inc.get("id"):
                try:
                    self.last_incident_id = int(inc["id"])
                    self.last_security_incident = inc
                    self.last_module = "security"
                except (TypeError, ValueError):
                    pass

        if "tracking" in tool_name:
            self.last_module = "tracking"
        elif "user" in tool_name:
            self.last_module = "users"
        elif "ticket" in tool_name:
            self.last_module = "tickets"
        elif "notification" in tool_name:
            self.last_module = "notifications"
        elif "log" in tool_name:
            self.last_module = "logs"
        elif "security" in tool_name or "suspicious" in tool_name:
            self.last_module = "security"
        elif "report" in tool_name or "platform" in tool_name:
            self.last_report_module = "platform_report"
            self.last_module = "reports"


def is_contextual_reference(message: str) -> bool:
    """Détecte les références au contexte précédent (ces, il, exporte-les…)."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_CONTEXTUAL_REFERENCE_RE.search(text))


def is_follow_up_message(message: str) -> bool:
    text = (message or "").strip()
    if len(text) > 120:
        return False
    return bool(_FOLLOW_UP_RE.search(text))


def is_tracking_follow_up(message: str, memory: "EntityMemory") -> bool:
    """Relance sur le dernier colis mémorisé."""
    text = (message or "").strip()
    if not memory.last_tracking_number or not text:
        return False
    if extract_tracking_number(text):
        return False
    return bool(_TRACKING_FOLLOWUP_RE.search(text) or is_follow_up_message(text))


def extract_tracking_number(text: str) -> str | None:
    from app.services.llm.tracking_extract import extract_tracking_number as _ext
    return _ext(text)


def resolve_message_with_entities(
    message: str,
    memory: EntityMemory,
) -> tuple[str, str | None]:
    """
    Résout les références implicites dans le message.
    Retourne (message_résolu, type_entité_résolue).
    """
    text = (message or "").strip()
    if not text:
        return text, None

    from app.services.llm.tracking_extract import extract_tracking_number

    if extract_tracking_number(text):
        return text, None

    if is_tracking_follow_up(text, memory):
        tn = memory.last_tracking_number
        resolved = f"Suivi colis {tn} — {text}"
        logger.info("[EntityMemory] tracking follow-up → %s", tn)
        return resolved, "tracking"

    if is_contextual_reference(text) and memory.last_notifications and _PRONOUN_NOTIFICATIONS_RE.search(text):
        logger.info("[EntityMemory] resolved notifications reference → %s items", len(memory.last_notifications))
        return f"{text} [contexte: {len(memory.last_notifications)} notifications mémorisées]", "notifications"

    if not is_follow_up_message(text) and not _PRONOUN_TRACKING_RE.search(text) and not is_contextual_reference(text):
        return text, None

    resolved_type: str | None = None

    if memory.last_tracking_number and (
        _PRONOUN_TRACKING_RE.search(text)
        or memory.last_module == "tracking"
        or re.search(r"\b(colis|package|tracking|suiv)\b", text, re.I)
    ):
        tn = memory.last_tracking_number
        resolved = f"{text} [contexte: colis {tn}]"
        logger.info("[EntityMemory] resolved tracking reference → %s", tn)
        return resolved, "tracking"

    if memory.last_user_id and _PRONOUN_USER_RE.search(text):
        resolved = f"{text} [contexte: utilisateur ID {memory.last_user_id}]"
        logger.info("[EntityMemory] resolved user reference → %s", memory.last_user_id)
        return resolved, "user"

    if memory.last_ticket_id and _PRONOUN_TICKET_RE.search(text):
        resolved = f"{text} [contexte: ticket ID {memory.last_ticket_id}]"
        return resolved, "ticket"

    if memory.last_tracking_number and is_follow_up_message(text):
        tn = memory.last_tracking_number
        resolved = f"Suivi colis {tn} — {text}"
        logger.info("[EntityMemory] follow-up → tracking %s", tn)
        return resolved, "tracking"

    return text, None


def build_entity_context_block(memory: EntityMemory) -> str:
    """Bloc injecté dans le contexte LLM."""
    parts = ["MÉMOIRE ENTITÉS SESSION (références « il », « ce colis », « ces notifications », etc.) :"]
    if memory.last_tracking_number:
        parts.append(f"- Dernier colis : {memory.last_tracking_number}")
    if memory.last_user_id:
        label = memory.last_user_email or f"ID {memory.last_user_id}"
        parts.append(f"- Dernier utilisateur : {label}")
    if memory.last_ticket_id:
        parts.append(f"- Dernier ticket : ID {memory.last_ticket_id}")
    if memory.last_incident_id:
        parts.append(f"- Dernier incident : ID {memory.last_incident_id}")
    if memory.last_notifications:
        parts.append(f"- Dernières notifications : {len(memory.last_notifications)} en mémoire")
    if memory.last_report_module:
        parts.append(f"- Dernier rapport : {memory.last_report_module}")
    if memory.last_result_summary:
        parts.append(f"- Résumé précédent : {memory.last_result_summary[:200]}")
    if len(parts) == 1:
        return ""
    return "\n".join(parts)
