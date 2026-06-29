"""Composition réponses agent e-mail admin."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.email.email_pending import (
    EMAIL_CONFIRM_MARKER_FR,
    build_email_pending_marker,
)
from app.services.admin_client.email.email_types import AdminEmailDraft, EmailPlan, EmailProfile


def _error_text(code: str, lang: str) -> str:
    fr = {
        "user_not_found": "Utilisateur destinataire introuvable.",
        "cannot_email_admin": "Impossible d'envoyer un e-mail à un compte administrateur via cet agent.",
        "recipient_no_email": "L'utilisateur n'a pas d'adresse e-mail.",
        "smtp_not_configured": "Service e-mail non configuré (vérifiez les variables SMTP_*).",
        "pending_parse_failed": "Impossible de relire le brouillon e-mail en attente.",
    }
    en = {
        "user_not_found": "Recipient user not found.",
        "cannot_email_admin": "Cannot send user email to an admin account via this agent.",
        "recipient_no_email": "The user has no email address.",
        "smtp_not_configured": "Email service not configured (check SMTP_* variables).",
        "pending_parse_failed": "Could not parse pending email draft.",
    }
    if code.startswith("email_send_failed:"):
        detail = code.split(":", 1)[-1]
        return (
            f"Échec envoi e-mail : {detail}"
            if lang == "fr"
            else f"Email delivery failed: {detail}"
        )
    table = fr if lang == "fr" else en
    return table.get(code, code)


def compose_draft_preview(
    draft: AdminEmailDraft,
    *,
    lang: str = "fr",
    attachment_requested: bool = False,
    attachment_found: bool = False,
    attachment_export_token: str | None = None,
) -> str:
    if lang == "en":
        header = "**Email draft — please review before sending**"
        to_l = "To"
        subj_l = "Subject"
        body_l = "Body"
        confirm = EMAIL_CONFIRM_MARKER_FR.replace(
            "Répondez par oui ou non pour confirmer l'envoi de cet e-mail",
            "Reply yes or no to confirm sending this email",
        )
    else:
        header = "**Brouillon e-mail — vérifiez avant envoi**"
        to_l = "Destinataire"
        subj_l = "Objet"
        body_l = "Corps"
        confirm = EMAIL_CONFIRM_MARKER_FR

    lines = [
        header,
        "",
        f"**{to_l} :** {draft.to}",
        f"**{subj_l} :** {draft.subject}",
        "",
        f"**{body_l} :**",
        "```",
        draft.body_text,
        "```",
    ]
    if attachment_requested:
        if attachment_found:
            lines.append(f"\n_Pièce jointe : {draft.attachment_filename}_")
        else:
            lines.append(
                "\n_Pièce jointe demandée mais fichier introuvable — envoi texte seul._"
                if lang == "fr"
                else "\n_Attachment requested but file not found — text only._"
            )
    lines.append(f"\n_{confirm}._")
    lines.append(
        build_email_pending_marker(
            to=draft.to,
            subject=draft.subject,
            body_text=draft.body_text,
            user_id=draft.user_id,
            attachment_export_token=attachment_export_token,
        )
    )
    return "\n".join(lines)


def compose_email_response(
    processed: dict[str, Any],
    plan: EmailPlan,
    *,
    lang: str = "fr",
    draft: AdminEmailDraft | None = None,
    send_result: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> str:
    if error_code:
        return _error_text(error_code, lang)

    if plan.needs_clarification:
        return plan.clarification_question

    if send_result:
        to = send_result.get("to") or "—"
        subj = send_result.get("subject") or ""
        if lang == "en":
            return f"Email sent to **{to}** — subject: « {subj} »."
        return f"E-mail envoyé à **{to}** — objet : « {subj} »."

    if draft and plan.profile in {EmailProfile.DRAFT, EmailProfile.CONFIRM}:
        return compose_draft_preview(
            draft,
            lang=lang,
            attachment_requested=bool(plan.attachment_export_token),
            attachment_found=bool(draft.attachment_bytes),
            attachment_export_token=plan.attachment_export_token,
        )

    if lang == "en":
        return "How can I help with user email?"
    return "Comment puis-je vous aider pour l'envoi d'e-mail utilisateur ?"
