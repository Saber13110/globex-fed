"""Classification intent envoi e-mail admin → utilisateur."""

from __future__ import annotations

import re

from app.services.admin_client.email.email_patterns import (
    extract_admin_note,
    extract_export_token_from_history,
    extract_recipient_email,
    is_send_user_email_message,
    wants_email_attachment,
)
from app.services.admin_client.email.email_patterns import _EMAIL_ADDR_RE
from app.services.admin_client.email.email_types import EmailPlan, EmailProfile, EmailTaskType
from app.services.admin_client.email.email_workspace import is_email_workspace


def default_clarify_question(lang: str) -> str:
    if lang == "en":
        return (
            "Who should receive the email (email address or user #id), "
            "and what message should I include?"
        )
    return (
        "À qui envoyer l'e-mail (adresse ou #id utilisateur) "
        "et quel message souhaitez-vous transmettre ?"
    )


def classify_email_intent(
    message: str,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> EmailPlan:
    text = (message or "").strip()
    if not is_send_user_email_message(text):
        return EmailPlan(task_type=EmailTaskType.ambiguous, raw_matches=["no_match"])

    recipient = extract_recipient_email(text)
    admin_note = extract_admin_note(text)
    if not admin_note:
        admin_note = _extract_freeform_note(text)
    if not admin_note:
        admin_note = _extract_note_fallback(text)

    attachment_token = None
    if wants_email_attachment(text):
        attachment_token = extract_export_token_from_history(history_text)

    plan = EmailPlan(
        task_type=EmailTaskType.send_user_email,
        profile=EmailProfile.DRAFT,
        recipient_email=recipient,
        admin_note=admin_note,
        attachment_export_token=attachment_token,
        raw_matches=["send_user_email"],
    )

    if not recipient and not re.search(r"#\s*\d+", text):
        plan.needs_clarification = True
        plan.profile = EmailProfile.CLARIFY
        plan.clarification_question = default_clarify_question(lang)
        return plan

    # Le brouillon est généré par le LLM selon le contexte — pas de message obligatoire de l'admin.
    return plan


def _extract_freeform_note(text: str) -> str:
    """Extrait le contenu après « pour lui dire que / pour l'informer que »."""
    m = re.search(
        r"\b("
        r"pour\s+(lui|l'|le)\s+(dire|informer|expliquer|pr[eé]venir)|"
        r"afin\s+de\s+(lui|le)\s+(dire|informer)|"
        r"message\s+suivant"
        r")\s*[:.]?\s*(.+)$",
        text,
        re.I | re.DOTALL,
    )
    if m:
        return m.group(2).strip()[:2000]
    return ""


def _extract_note_fallback(text: str) -> str:
    """Dernier recours : texte restant après retrait des mots-clés d'envoi."""
    t = _EMAIL_ADDR_RE.sub("", text or "")
    t = re.sub(
        r"\b("
        r"envoie|envoyer|mail|e-mail|email|courriel|un|une|le|la|à|a|pour|"
        r"utilisateur|user|compte|client|lui|leur"
        r")\b",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+", " ", t).strip(" .,-:;")
    return t[:2000] if len(t) >= 12 else ""
