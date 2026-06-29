"""Patterns détection envoi e-mail admin → utilisateur."""

from __future__ import annotations

import re
import unicodedata

_EMAIL_ADDR_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_SEND_USER_EMAIL_RE = re.compile(
    r"\b("
    r"(envoie|envoyer|écrire|ecrire|notifie|notifier|pr[eé]venir|prevenir|"
    r"fais\s+partir|fait\s+partir|transmet|transmettre|contacte|contacter)"
    r".{0,45}(mail|e-mail|email|courriel)|"
    r"(mail|e-mail|email|courriel).{0,45}"
    r"(à|a|pour|to|destinataire).{0,45}(utilisateur|user|compte|client|@)|"
    r"envoie.{0,20}(lui|leur).{0,25}(mail|e-mail|email)"
    r")\b",
    re.I,
)

_BULK_RE = re.compile(
    r"\b(bulk|en\s+masse|tous\s+les\s+(utilisateurs|users|clients)|mass\s+mail|mailing)\b",
    re.I,
)

_ADMIN_RECIPIENTS_RE = re.compile(
    r"\b(administrateurs?|admins?)\b.{0,30}(mail|e-mail|email)|"
    r"(mail|e-mail|email).{0,30}(administrateurs?|admins?)\b",
    re.I,
)

_BODY_EXTRACT_RE = re.compile(
    r"\b("
    r"pour\s+lui\s+dire|pour\s+leur\s+dire|disant\s+que|afin\s+de\s+lui|"
    r"message\s*:|contenu\s*:|texte\s*:|objet\s*:"
    r")\s*[:.]?\s*(.+)$",
    re.I | re.DOTALL,
)

_ATTACHMENT_RE = re.compile(
    r"\b(pi[eè]ce\s+jointe|pj|avec\s+(le\s+)?pdf|joint\s+le\s+pdf|attach)\b",
    re.I,
)

_EXPORT_TOKEN_RE = re.compile(r"\bexport_token['\"]?\s*[:=]\s*['\"]?([a-f0-9]{32})\b", re.I)

_USER_ADMIN_ACTION_RE = re.compile(
    r"\b(suspend(?:re|ez)?|bloqu(?:er|ez)?|r[eé]activ(?:er|ez)?)\b",
    re.I,
)
_TICKET_ADMIN_ACTION_RE = re.compile(
    r"\b("
    r"(r[eé]pond(?:re|ez)?|reply).{0,35}tickets?|"
    r"tickets?.{0,35}(r[eé]pond(?:re|ez)?|reply)|"
    r"(marque(?:r|z)?|r[eé]sol(?:u(?:e|es)?|v(?:e|ez|er)?)|resolve|ferme(?:r|z)?|close).{0,35}tickets?|"
    r"tickets?.{0,35}(marque(?:r|z)?|r[eé]sol(?:u(?:e|es)?|v(?:e|ez|er)?)|resolve|ferme(?:r|z)?|close)"
    r")\b",
    re.I,
)


def normalize_email_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def is_bulk_email_message(message: str) -> bool:
    return bool(_BULK_RE.search(normalize_email_text(message)))


def is_admin_recipients_email(message: str) -> bool:
    return bool(_ADMIN_RECIPIENTS_RE.search(normalize_email_text(message)))


_REPORT_CONTEXT_RE = re.compile(r"\b(rapports?|reports?|exports?|centre\s+de\s+rapports?)\b", re.I)
_USER_NOTIFY_CONTEXT_RE = re.compile(
    r"\b("
    r"ticket|tickets?|compte|utilisateur|user|client|"
    r"informer|dire|trait[eé]|suspend|r[eé]activ|message|"
    r"acc[eè]s|mot\s+de\s+passe|incident|avertir"
    r")\b",
    re.I,
)


def is_report_share_email_message(message: str) -> bool:
    """E-mail de partage rapport — pas notification utilisateur."""
    text = normalize_email_text(message)
    if not text:
        return False
    if not re.search(r"\b(mail|e-mail|email|courriel|envoie|envoyer|partage|share)\b", text, re.I):
        return False
    return bool(_REPORT_CONTEXT_RE.search(text))


def is_users_action_email_combo(message: str) -> bool:
    """Action utilisateur (suspend/réactiver) + notification e-mail — agent users, pas e-mail standalone."""
    text = normalize_email_text(message)
    if not text or not _USER_ADMIN_ACTION_RE.search(text):
        return False
    from app.services.admin_client.email.email_action_offer import wants_notify_user_by_email

    return wants_notify_user_by_email(text)


def is_tickets_action_email_combo(message: str) -> bool:
    """Action ticket (réponse/résolution) + notification e-mail — agent tickets."""
    text = normalize_email_text(message)
    if not text or not _TICKET_ADMIN_ACTION_RE.search(text):
        return False
    from app.services.admin_client.email.email_action_offer import wants_notify_user_by_email

    return wants_notify_user_by_email(text)


def is_admin_action_email_combo(message: str) -> bool:
    return is_users_action_email_combo(message) or is_tickets_action_email_combo(message)


def is_direct_user_account_action(message: str) -> bool:
    """
    Action admin directe sur un compte identifié (e-mail explicite).
    Exclut « suspendre depuis ce log » — agent Logs dans ce cas.
    """
    text = normalize_email_text(message)
    if not text or not _EMAIL_ADDR_RE.search(text):
        return False
    from app.services.admin_client.logs.logs_patterns import SUSPEND_FROM_LOG_RE

    if SUSPEND_FROM_LOG_RE.search(text):
        return False
    if is_users_action_email_combo(text):
        return True
    if re.search(
        r"\b(suspend(?:re|ez)?|bloqu(?:er|ez)?|r[eé]activ(?:er|ez)?|supprim(?:er|ez)?)\b",
        text,
        re.I,
    ):
        return True
    return False


def should_defer_logs_to_users(message: str) -> bool:
    """Le message relève de l'agent Utilisateurs, pas des journaux d'activité."""
    return is_direct_user_account_action(message) or is_users_action_email_combo(message)


def is_send_user_email_message(message: str) -> bool:
    text = normalize_email_text(message)
    if not text or is_bulk_email_message(text) or is_admin_recipients_email(text):
        return False
    if is_admin_action_email_combo(text):
        return False
    if is_report_share_email_message(text) and not _USER_NOTIFY_CONTEXT_RE.search(text):
        return False
    has_mail = bool(re.search(r"\b(mail|e-mail|email|courriel)\b", text, re.I))
    has_send = bool(
        re.search(
            r"\b(envoie|envoyer|écrire|ecrire|notifie|notifier|pr[eé]venir|prevenir|contacte)\b",
            text,
            re.I,
        )
    )
    has_addr = bool(_EMAIL_ADDR_RE.search(text))
    has_user_ctx = bool(_USER_NOTIFY_CONTEXT_RE.search(text))
    if has_addr and (has_mail or has_send):
        return True
    if has_mail and has_send and has_user_ctx:
        return True
    if has_send and has_addr and has_user_ctx:
        return True
    return bool(_SEND_USER_EMAIL_RE.search(text))


def extract_recipient_email(message: str) -> str | None:
    m = _EMAIL_ADDR_RE.search(message or "")
    return m.group(0).lower() if m else None


def extract_admin_note(message: str) -> str:
    text = (message or "").strip()
    m = _BODY_EXTRACT_RE.search(text)
    if m:
        return m.group(2).strip()[:2000]
    for sep in (" — ", " - ", " : ", ": "):
        if sep in text:
            tail = text.split(sep, 1)[-1].strip()
            if len(tail) >= 12 and not _EMAIL_ADDR_RE.fullmatch(tail):
                return tail[:2000]
    return ""


def wants_email_attachment(message: str) -> bool:
    return bool(_ATTACHMENT_RE.search(message or ""))


def extract_export_token_from_history(history_text: str) -> str | None:
    m = _EXPORT_TOKEN_RE.search(history_text or "")
    return m.group(1) if m else None


def score_email_utterance(message: str) -> float:
    if is_send_user_email_message(message):
        return 3.0
    return 0.0
