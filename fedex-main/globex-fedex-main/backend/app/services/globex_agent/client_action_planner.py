"""Planification actions client — évite confusion avec export PDF."""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

# Envoi notification / e-mail à un client — jamais un export
_CLIENT_NOTIFY_RE = re.compile(
    r"\b(?:"
    r"(?:envo(?:ie|ye|yer)|send).{0,60}(?:une\s+)?notifications?"
    r"|notifi(?:e|ez|er|cation).{0,60}(?:au\s+)?(?:clien|client|utilisateur|user|employ[eé])"
    r"|(?:envo(?:ie|ye|yer)|send).{0,60}(?:un\s+)?(?<![@\w])(?:mail|email|e-mail).{0,40}(?:au\s+)?(?:clien|client|utilisateur)"
    r")\b",
    re.I,
)

COMM_ACTION_TOOLS = frozenset({
    "notify_user",
    "notify_user_warning",
    "notify_employee",
    "send_notification",
    "send_client_email",
    "send_email",
    "suspend_user",
    "reactivate_user",
    "reply_support_ticket",
    "close_ticket",
    "escalate_ticket",
})

_CLIENT_EMAIL_RE = re.compile(
    r"\b(?:envo(?:ie|ye|yer)|send).{0,80}(?:un\s+)?(?<![@\w])(?:mail|email|e-mail)\b",
    re.I,
)

_SEND_FOLLOWUP_RE = re.compile(
    r"\b(?:envo(?:ie|ye|yer)|send)\s+(?:le|la|lui|ça|ca|cela)\b",
    re.I,
)

_MAIL_CONTEXT_RE = re.compile(
    r"\b(?:mail|email|e-mail|notification|msg|message)\b",
    re.I,
)

_CREER_MAIL_RE = re.compile(r"\bcre[eé]r?\s+un\s+(?:mail|email|message)\b", re.I)

# Export explicite — ne pas confondre avec envoi mail/notification
_EXPORT_EXPLICIT_RE = re.compile(
    r"\b(export|exporter|pdf|excel|xlsx|t[eé]l[eé]charger|fichier)\b",
    re.I,
)

# Outils autorisés quand l'admin veut contacter un client (masque export_* à Ollama)
_CLIENT_COMM_TOOL_NAMES = frozenset({
    "search_users",
    "analyze_users",
    "get_admin_users",
    "notify_user",
    "notify_user_warning",
    "notify_employee",
    "send_notification",
    "send_client_email",
    "send_email",
    "draft_client_email",
})

_THANKS_RE = re.compile(r"\b(remerciement|remercie|thank\s*you|merci\s+pour)\b", re.I)


def build_client_action_context(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Texte combiné message + historique récent pour détecter une intention d'envoi."""
    parts: list[str] = []
    for item in (history or [])[-8:]:
        content = (item.get("content") or "").strip()
        if content:
            parts.append(content)
    current = (message or "").strip()
    if current:
        parts.append(current)
    return " ".join(parts)


def is_client_communication_action(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """True si la phrase vise l'envoi à un client, pas un export fichier."""
    text = build_client_action_context(message, history) if history else (message or "")
    if _EXPORT_EXPLICIT_RE.search(text):
        return False
    if _CLIENT_NOTIFY_RE.search(text):
        return True
    if _CLIENT_EMAIL_RE.search(text):
        return True
    if _SEND_FOLLOWUP_RE.search(text) and _MAIL_CONTEXT_RE.search(text):
        return True
    if _CREER_MAIL_RE.search(text) and re.search(r"\benvo", text, re.I):
        return True
    return False


def filter_tools_for_client_communication(tools: list[Any]) -> list[Any]:
    """Réduit le bruit pour Ollama — pas d'export quand l'admin veut envoyer un message."""
    names = {t.name for t in tools}
    allowed = _CLIENT_COMM_TOOL_NAMES & names
    if not allowed:
        return tools
    return [t for t in tools if t.name in allowed]


def extract_email_from_message(message: str) -> str | None:
    m = _EMAIL_RE.search(message or "")
    return m.group(0).strip() if m else None


def _extract_recipient_query(text: str) -> str | None:
    """Nom ou email du destinataire pour search_users."""
    email = extract_email_from_message(text)
    if email:
        return email
    m = re.search(
        r"(?:à|a|au|pour)\s+(?:l['']?)?(?:utilisateur|client|user)?\s*([a-z0-9._-]{2,40})",
        text,
        re.I,
    )
    if m:
        token = m.group(1).lower()
        if token not in {"le", "la", "lui", "un", "une", "mail", "email", "msg", "message"}:
            return token
    return None


def _default_thank_you_body() -> str:
    return (
        "Cher(e) client(e),\n\n"
        "Je tiens à vous remercier sincèrement pour votre compréhension et votre soutien.\n\n"
        "Cordialement,\nL'équipe Globex FedEx"
    )


def _extract_message_body(message: str) -> str:
    text = (message or "").strip()
    if _THANKS_RE.search(text):
        return _default_thank_you_body()
    for sep in (":", "—", "–", "-"):
        if sep in text:
            tail = text.split(sep, 1)[-1].strip()
            if tail and "@" not in tail[:20] and len(tail) > 12:
                return tail[:2000]
    return "Message de l'administrateur Globex FedEx."


def _wants_email(text: str) -> bool:
    return bool(
        _CLIENT_EMAIL_RE.search(text)
        or (_CREER_MAIL_RE.search(text) and _MAIL_CONTEXT_RE.search(text))
        or (_SEND_FOLLOWUP_RE.search(text) and _MAIL_CONTEXT_RE.search(text))
    )


def plan_client_action_tools(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> list[tuple[str, dict[str, Any]]] | None:
    """Route déterministe search_users → notify_user / send_client_email."""
    context = build_client_action_context(message, history)
    if not is_client_communication_action(message, history=history):
        return None

    email = extract_email_from_message(context)
    body = _extract_message_body(message)
    subject = "Remerciement — Globex FedEx" if _THANKS_RE.search(context) else "Message — Globex FedEx"

    steps: list[tuple[str, dict[str, Any]]] = []
    recipient_query = _extract_recipient_query(context)
    if not email and recipient_query:
        steps.append(("search_users", {"query": recipient_query, "limit": 5}))

    if _CLIENT_NOTIFY_RE.search(context) and not _CLIENT_EMAIL_RE.search(context):
        notify_args: dict[str, Any] = {
            "title": "Message administrateur",
            "message": body,
            "type": "system_alert",
        }
        if email:
            notify_args["email"] = email
        steps.append(("notify_user", notify_args))
    elif _wants_email(context) or _CLIENT_EMAIL_RE.search(context):
        mail_args: dict[str, Any] = {
            "subject": subject,
            "body": body if body != "Message de l'administrateur Globex FedEx." else (
                "Ceci est un mail envoyé par l'administrateur Globex FedEx."
            ),
        }
        if email:
            mail_args["to"] = email
            mail_args["email"] = email
        steps.append(("send_client_email", mail_args))
    else:
        notify_args: dict[str, Any] = {
            "title": "Message administrateur",
            "message": body,
            "type": "system_alert",
        }
        if email:
            notify_args["email"] = email
        steps.append(("notify_user", notify_args))

    return steps or None


def enrich_send_args_from_search(
    args: dict[str, Any],
    tool_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    """Complète send_client_email / notify_user après search_users."""
    out = dict(args or {})
    if out.get("email") or out.get("user_id"):
        return out
    for item in reversed(tool_payloads):
        if item.get("name") != "search_users":
            continue
        resp = item.get("response") if isinstance(item.get("response"), dict) else {}
        users = resp.get("users") if isinstance(resp.get("users"), list) else []
        if not users:
            continue
        first = users[0]
        if isinstance(first, dict):
            if first.get("email"):
                out.setdefault("email", first["email"])
            if first.get("id"):
                out.setdefault("user_id", first["id"])
        break
    return out
