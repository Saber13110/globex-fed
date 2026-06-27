"""État conversationnel du copilot admin — contexte, pas mots-clés isolés."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

CopilotModule = Literal[
    "notifications",
    "logs",
    "tracking",
    "users",
    "tickets",
    "conversations",
    "reports",
    "security",
    "knowledge",
    "dashboard",
]

ExportFormat = Literal["pdf", "xlsx"]


@dataclass
class CopilotConversationState:
    last_module: str | None = None
    last_intent: str | None = None
    last_query_type: str | None = None
    last_tool_used: str | None = None
    last_items: list[dict[str, Any]] = field(default_factory=list)
    last_payload: dict[str, Any] | None = None
    last_result_summary: str | None = None
    last_exportable_result: bool = False
    last_limit: int | None = None
    last_format: str | None = None
    last_entity_ids: list[int] = field(default_factory=list)
    last_tracking_numbers: list[str] = field(default_factory=list)
    last_user_ids: list[int] = field(default_factory=list)
    last_notification_ids: list[int] = field(default_factory=list)
    last_report_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_module": self.last_module,
            "last_intent": self.last_intent,
            "last_query_type": self.last_query_type,
            "last_tool_used": self.last_tool_used,
            "last_items": self.last_items[:50],
            "last_payload": self.last_payload,
            "last_result_summary": self.last_result_summary,
            "last_exportable_result": self.last_exportable_result,
            "last_limit": self.last_limit,
            "last_format": self.last_format,
            "last_entity_ids": self.last_entity_ids[:50],
            "last_tracking_numbers": self.last_tracking_numbers[:20],
            "last_user_ids": self.last_user_ids[:50],
            "last_notification_ids": self.last_notification_ids[:50],
            "last_report_context": self.last_report_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CopilotConversationState:
        if not data:
            return cls()
        return cls(
            last_module=data.get("last_module"),
            last_intent=data.get("last_intent"),
            last_query_type=data.get("last_query_type"),
            last_tool_used=data.get("last_tool_used"),
            last_items=list(data.get("last_items") or [])[:50],
            last_payload=data.get("last_payload"),
            last_result_summary=data.get("last_result_summary"),
            last_exportable_result=bool(data.get("last_exportable_result")),
            last_limit=data.get("last_limit"),
            last_format=data.get("last_format"),
            last_entity_ids=list(data.get("last_entity_ids") or [])[:50],
            last_tracking_numbers=list(data.get("last_tracking_numbers") or [])[:20],
            last_user_ids=list(data.get("last_user_ids") or [])[:50],
            last_notification_ids=list(data.get("last_notification_ids") or [])[:50],
            last_report_context=data.get("last_report_context"),
        )


@dataclass
class ResolvedCopilotTurn:
    kind: Literal["gemini", "contextual_export", "clarify_export", "security_block"]
    module: str | None = None
    export_format: ExportFormat | None = None
    limit: int | None = None
    reason: str | None = None


_MODULE_FROM_TEXT: list[tuple[str, re.Pattern[str]]] = [
    ("notifications", re.compile(r"\b(notifs?|notifications?|alertes?)\b", re.I)),
    ("logs", re.compile(r"\b(logs?|journaux)\b", re.I)),
    ("tracking", re.compile(r"\b(tracking|exp[eé]ditions?|colis|shipments?)\b", re.I)),
    ("users", re.compile(r"\b(users?|utilisateurs?|comptes?|admins?)\b", re.I)),
    ("tickets", re.compile(r"\b(tickets?|support)\b", re.I)),
    ("conversations", re.compile(r"\b(conversations?|discussions?|chats?)\b", re.I)),
    ("security", re.compile(r"\b(s[eé]curit[eé]|incidents?|ids)\b", re.I)),
    ("knowledge", re.compile(r"\b(connaissances?|documents?|knowledge)\b", re.I)),
    ("reports", re.compile(r"\b(rapports?|bilan|synth[eè]se)\b", re.I)),
]

_TOOL_TO_MODULE: dict[str, str] = {
    "analyze_notifications": "notifications",
    "analyze_logs": "logs",
    "export_activity_logs_pdf": "logs",
    "export_activity_logs_excel": "logs",
    "analyze_tracking": "tracking",
    "fedex_track_package": "tracking",
    "export_tracking_status_pdf": "tracking",
    "export_tracking_pdf": "tracking",
    "analyze_users": "users",
    "export_users_pdf": "users",
    "analyze_tickets": "tickets",
    "export_tickets_pdf": "tickets",
    "analyze_conversations": "conversations",
    "export_conversations_pdf": "conversations",
    "analyze_security": "security",
    "analyze_reports": "reports",
    "get_platform_stats": "dashboard",
    "search_knowledge": "knowledge",
    "list_knowledge_documents": "knowledge",
    "export_notifications_pdf": "notifications",
    "export_generic_result_pdf": "generic",
}

_PDF_RE = re.compile(r"\bpdf\b", re.I)
_XLSX_RE = re.compile(r"\b(xlsx|excel)\b", re.I)
_LIMIT_RE = re.compile(
    r"\b(\d+)\s*(?:derni[eè]res?|derniers?|last|recentes?|r[eé]centes?)?\b",
    re.I,
)

# Demande de lecture / liste — jamais un export
_DATA_LIST_REQUEST_RE = re.compile(
    r"\b("
    r"donne|montre|affiche|liste|lister|voir|quels?|quelles?|combien|"
    r"r[eé]sume|resume|synth[eè]se|synthese|qu'?est|activit[eé]|activite|"
    r"y\s+a|surveiller|pass[eé]|r[eé]cent|derni[eè]r|derno|choses?\s+importantes"
    r")\b",
    re.I,
)

# Relance export pure (sans nouvelle demande de données)
_EXPORT_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"g[eé]n[eè]r|export|mets?|met|fais|envoie|t[eé]l[eé]charge|"
    r"sous\s+form|sous\s+forme|en\s+pdf|format\s+pdf|"
    r"je\s+veux.{0,24}(pdf|excel|xlsx)|pardon|plut[oô]t"
    r")\b",
    re.I,
)
_EXPORT_PRONOUN_RE = re.compile(
    r"\b(les|le|la|ça|ca|ceux|celles|cela|même|meme|ces|celles.?ci|ceux.?ci|celles.?là|ceux.?là)\b",
    re.I,
)

# Résultat assistant contenant de vraies données (pas salutation / capacités)
_DATA_RESULT_MARKERS = re.compile(
    r"(voici les|affichée\(s\)|sur \d+ au total|élément\(s\)|"
    r"^\s*-\s*\*\*|export pdf prêt|non lue\)|ticket\(s\)|compte\(s\))",
    re.I | re.M,
)
_GREETING_OR_CAPABILITIES = re.compile(
    r"\b(copilot super admin|que souhaitez-vous|je peux vous aider|"
    r"voici ce que je peux faire|mode actuel)\b",
    re.I,
)

_ASSISTANT_MODULE_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("notifications", re.compile(r"\b(notifications?|Tracking Request|notif)\b", re.I)),
    ("logs", re.compile(r"\b(journal|activit[eé] syst[eè]me|entrées? d'activit)\b", re.I)),
    ("tracking", re.compile(r"\b(colis|exp[eé]dition.{0,20}retard|numéro de suivi)\b", re.I)),
    ("users", re.compile(r"\b(compte\(s\)|utilisateur.{0,20}suspendu)\b", re.I)),
    ("tickets", re.compile(r"\b(ticket.{0,20}ouvert|tickets support)\b", re.I)),
]


def parse_limit_from_message(message: str, *, default: int | None = None) -> int | None:
    from app.services.ai_assistant.export_normalize import parse_export_limit

    return parse_export_limit(message, default=default)


def detect_export_format(message: str) -> ExportFormat | None:
    text = (message or "").lower()
    if _PDF_RE.search(text):
        return "pdf"
    if _XLSX_RE.search(text):
        return "xlsx"
    if re.search(r"\bexporte[rz]?\b", text):
        return "pdf"
    return None


def infer_module_from_message(message: str) -> str | None:
    text = message or ""
    found: list[str] = []
    for name, pattern in _MODULE_FROM_TEXT:
        if pattern.search(text):
            found.append(name)
    if len(found) == 1:
        return found[0]
    if "notifications" in found:
        return "notifications"
    if "tracking" in found and "notifications" not in found:
        return "tracking"
    return found[0] if found else None


def infer_module_from_assistant_text(content: str) -> str | None:
    if not _assistant_message_is_data_result(content):
        return None
    for name, pattern in _ASSISTANT_MODULE_HINTS:
        if pattern.search(content or ""):
            return name
    return None


def _assistant_message_is_data_result(content: str) -> bool:
    text = (content or "").strip()
    if not text or _GREETING_OR_CAPABILITIES.search(text):
        return False
    return bool(_DATA_RESULT_MARKERS.search(text))


def is_data_list_request(message: str) -> bool:
    """Demande de consulter/lister des données — pas un export."""
    text = (message or "").strip()
    if not text:
        return False
    if detect_export_format(text) and not _DATA_LIST_REQUEST_RE.search(text):
        return False
    if _DATA_LIST_REQUEST_RE.search(text):
        return True
    mod = infer_module_from_message(text)
    if mod and parse_limit_from_message(text) and not detect_export_format(text):
        return True
    return False


def is_export_only_message(message: str, state: CopilotConversationState) -> bool:
    """
    Export contextuel uniquement : format explicite ou relance sur résultat précédent.
    Jamais pour une demande « donne-moi / liste / montre ».
    """
    text = (message or "").strip()
    if not text or is_data_list_request(text):
        return False

    export_fmt = detect_export_format(text)
    explicit_module = infer_module_from_message(text)

    if export_fmt and explicit_module:
        return True

    if export_fmt and state.last_exportable_result:
        return True

    if export_fmt and not explicit_module and not state.last_exportable_result:
        return len(text.split()) <= 10

    if (
        state.last_exportable_result
        and _EXPORT_FOLLOW_UP_RE.search(text)
        and (_EXPORT_PRONOUN_RE.search(text) or len(text) < 60)
    ):
        return True

    return False


_EXPORT_TOOL_IN_MSG = re.compile(
    r"\[(?:Outils|Tools)\s*:\s*(export_[\w]+|generate_text_pdf)\]",
    re.I,
)
_EXPORT_READY_RE = re.compile(r"export\s+(?:pdf|excel)\s+pr", re.I)
_EXPORT_FILENAME_HINT = re.compile(
    r"\b(notifications|users|tracking|tickets|conversations|activity-logs)-(\d+)",
    re.I,
)


def infer_last_export_from_history(
    messages: list[dict[str, str]] | None,
) -> tuple[str | None, int | None, str | None]:
    """Déduit module / limite / format du dernier export assistant."""
    if not messages:
        return None, None, None
    for item in reversed(messages):
        role = (item.get("role") or "").lower()
        if role not in {"assistant", "agent", "copilot"}:
            continue
        content = item.get("content") or ""
        tool_match = _EXPORT_TOOL_IN_MSG.search(content)
        if tool_match:
            tool = tool_match.group(1).lower()
            mod = _TOOL_TO_MODULE.get(tool)
            if mod:
                limit = parse_limit_from_message(content)
                fh = _EXPORT_FILENAME_HINT.search(content)
                if fh and not limit:
                    try:
                        limit = int(fh.group(2))
                    except (TypeError, ValueError):
                        pass
                last_fmt: ExportFormat = "xlsx" if "excel" in tool else "pdf"
                return mod, limit, last_fmt
        if _EXPORT_READY_RE.search(content) or _DATA_RESULT_MARKERS.search(content):
            mod = infer_module_from_assistant_text(content)
            if not mod:
                fh = _EXPORT_FILENAME_HINT.search(content)
                if fh:
                    mod = fh.group(1).lower()
                    if mod == "activity-logs":
                        mod = "logs"
            if mod:
                limit = parse_limit_from_message(content)
                fh = _EXPORT_FILENAME_HINT.search(content)
                if fh and not limit:
                    try:
                        limit = int(fh.group(2))
                    except (TypeError, ValueError):
                        pass
                last_fmt = "xlsx" if re.search(r"\bexcel\b", content, re.I) else "pdf"
                return mod, limit, last_fmt
    return None, None, None


def rebuild_state_from_history(messages: list[dict[str, str]] | None) -> CopilotConversationState:
    """Reconstruit l'état depuis un vrai résultat assistant (pas salutation)."""
    state = CopilotConversationState()
    mod, limit, last_fmt = infer_last_export_from_history(messages)
    if mod:
        state.last_module = mod
        state.last_exportable_result = True
        state.last_query_type = "export"
        if limit:
            state.last_limit = limit
        if last_fmt:
            state.last_format = last_fmt
        return state
    if not messages:
        return state
    for item in reversed(messages):
        role = (item.get("role") or "").lower()
        content = (item.get("content") or "").strip()
        if role not in {"assistant", "agent", "copilot"} or not content:
            continue
        if not _assistant_message_is_data_result(content):
            continue
        mod = infer_module_from_assistant_text(content)
        if mod:
            state.last_module = mod
            state.last_exportable_result = True
            state.last_query_type = "list"
            lim = parse_limit_from_message(content, default=5)
            if lim:
                state.last_limit = lim
            break
    return state


def merge_conversation_state(
    client_state: dict[str, Any] | None,
    messages: list[dict[str, str]] | None,
) -> CopilotConversationState:
    state = CopilotConversationState.from_dict(client_state)
    if not state.last_exportable_result:
        inferred = rebuild_state_from_history(messages)
        if inferred.last_module and inferred.last_exportable_result:
            state.last_module = state.last_module or inferred.last_module
            state.last_limit = state.last_limit or inferred.last_limit
            state.last_format = state.last_format or inferred.last_format
            state.last_exportable_result = True
    return state


def resolve_copilot_turn(
    message: str,
    state: CopilotConversationState,
    *,
    messages: list[dict[str, str]] | None = None,
) -> ResolvedCopilotTurn:
    """
    Résout les exports contextuels uniquement — les listes passent par Gemini.
  """
    from app.services.prompt_guard_service import is_strict_security_attack

    if is_strict_security_attack(message):
        return ResolvedCopilotTurn(kind="security_block", reason="strict_security")

    if not is_export_only_message(message, state):
        return ResolvedCopilotTurn(kind="gemini")

    export_fmt = detect_export_format(message) or state.last_format or "pdf"
    explicit_module = infer_module_from_message(message)
    module = explicit_module or state.last_module
    limit = parse_limit_from_message(message) or state.last_limit

    if not module and messages:
        hist_mod, hist_limit, hist_fmt = infer_last_export_from_history(messages)
        if hist_mod:
            module = hist_mod
            limit = limit or hist_limit
            if not detect_export_format(message) and hist_fmt:
                export_fmt = hist_fmt
        else:
            for item in reversed(messages):
                role = (item.get("role") or "").lower()
                if role not in {"assistant", "agent", "copilot"}:
                    continue
                content = item.get("content") or ""
                if not _assistant_message_is_data_result(content):
                    continue
                mod = infer_module_from_assistant_text(content)
                if mod:
                    module = mod
                    break

    if not module:
        return ResolvedCopilotTurn(kind="clarify_export", export_format=export_fmt)

    if module == "logs" and explicit_module and explicit_module != "logs":
        module = explicit_module

    return ResolvedCopilotTurn(
        kind="contextual_export",
        module=module,
        export_format=export_fmt if export_fmt in ("pdf", "xlsx") else "pdf",
        limit=limit,
    )


def _extract_entity_ids(items: list[dict[str, Any]], module: str) -> dict[str, list]:
    ids: dict[str, list] = {
        "entity_ids": [],
        "tracking_numbers": [],
        "user_ids": [],
        "notification_ids": [],
    }
    for row in items:
        if not isinstance(row, dict):
            continue
        if row.get("id") is not None:
            try:
                ids["entity_ids"].append(int(row["id"]))
            except (TypeError, ValueError):
                pass
        if module == "notifications" and row.get("id") is not None:
            try:
                ids["notification_ids"].append(int(row["id"]))
            except (TypeError, ValueError):
                pass
        if row.get("user_id") is not None:
            try:
                ids["user_ids"].append(int(row["user_id"]))
            except (TypeError, ValueError):
                pass
        tn = row.get("tracking_number")
        if tn:
            ids["tracking_numbers"].append(str(tn))
    return ids


def update_state_after_tools(
    state: CopilotConversationState,
    *,
    tools_used: list[str],
    tool_payloads: list[dict[str, Any]],
    reply_summary: str | None = None,
) -> CopilotConversationState:
    if not tools_used:
        return state
    primary = tools_used[-1]
    state.last_tool_used = primary
    state.last_module = _TOOL_TO_MODULE.get(primary, state.last_module)
    if primary.startswith("analyze_") or primary.startswith("get_"):
        state.last_intent = primary
    payload_entry = next(
        (p for p in reversed(tool_payloads) if p.get("name") == primary),
        tool_payloads[-1] if tool_payloads else None,
    )
    if not payload_entry:
        return state
    response = payload_entry.get("response") or {}
    if response.get("status") not in (None, "ok"):
        return state
    data = {k: v for k, v in response.items() if k != "status"}
    state.last_payload = data
    state.last_exportable_result = True
    state.last_query_type = "list"
    sample = (
        data.get("sample")
        or data.get("tickets")
        or data.get("documents")
        or data.get("passages")
        or data.get("users")
    )
    if isinstance(sample, list):
        state.last_items = [x for x in sample if isinstance(x, dict)][:50]
        extracted = _extract_entity_ids(state.last_items, state.last_module or "")
        state.last_entity_ids = extracted["entity_ids"]
        state.last_notification_ids = extracted["notification_ids"]
        state.last_user_ids = extracted["user_ids"]
        state.last_tracking_numbers = extracted["tracking_numbers"]
    if data.get("count") and not state.last_limit:
        try:
            state.last_limit = int(data["count"])
        except (TypeError, ValueError):
            pass
    if reply_summary:
        state.last_result_summary = reply_summary[:500]
    return state


def build_state_server_instruction(state: CopilotConversationState) -> str:
    if not state.last_module:
        return ""
    parts = [
        f"COPILOT_STATE — dernier module traité : **{state.last_module}**",
    ]
    if state.last_limit:
        parts.append(f"dernier volume : {state.last_limit}")
    if state.last_items:
        parts.append(f"{len(state.last_items)} élément(s) en mémoire de session")
    if state.last_result_summary:
        parts.append(f"résumé : {state.last_result_summary[:200]}")
    parts.append(
        "Relances export (« ces », « les », « en PDF », « mets ça ») = ce module. "
        "PDF est un format, pas un module — ne jamais supposer les logs par défaut."
    )
    return "\n".join(parts)
