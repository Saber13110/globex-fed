"""Envoi SMTP des exports client avec pièce jointe."""

from __future__ import annotations

import logging

from app.models.user import User
from app.services.email_service import is_email_configured, send_email_with_attachment

logger = logging.getLogger(__name__)

_MIME = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _lang(user: User) -> str:
    code = (user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def send_client_export_email(
    user: User,
    *,
    file_bytes: bytes,
    filename: str,
    fmt: str,
    doc_label: str,
) -> bool:
    if not file_bytes:
        return False
    to = (getattr(user, "email", None) or "").strip()
    if not to or not is_email_configured():
        return False
    lang = _lang(user)
    mime = _MIME.get(fmt.lower(), "application/octet-stream")
    if lang == "en":
        subject = f"[Globex FedEx] {doc_label}"
        body = (
            f"Hello {user.full_name or ''},\n\n"
            f"Please find attached your {doc_label.lower()} ({filename}).\n\n"
            f"You can also download it from your Globex FedEx chat.\n\n"
            f"— FedEx Globex Agent"
        )
    else:
        subject = f"[Globex FedEx] {doc_label}"
        body = (
            f"Bonjour {user.full_name or ''},\n\n"
            f"Veuillez trouver ci-joint : {doc_label} ({filename}).\n\n"
            f"Vous pouvez aussi le télécharger depuis votre chat Globex FedEx.\n\n"
            f"— Agent FedEx Globex"
        )
    try:
        sent = send_email_with_attachment(
            to=to,
            subject=subject,
            body_text=body,
            attachment_bytes=file_bytes,
            attachment_filename=filename,
            attachment_mime=mime,
        )
        if sent:
            logger.info("Export %s envoyé par mail à %s (%s)", fmt, to, filename)
        return sent
    except Exception:
        logger.exception("Échec envoi export %s par mail", filename)
        return False


def build_email_suffix(user: User, *, sent: bool, smtp_ok: bool, has_email: bool, lang: str | None = None) -> str:
    code = lang or _lang(user)
    email = (getattr(user, "email", None) or "").strip()
    if not has_email:
        if code == "en":
            return "\n\n_Add an email address to your account to receive exports by mail._"
        return "\n\n_Ajoutez une adresse e-mail à votre compte pour recevoir les exports par mail._"
    if not smtp_ok:
        if code == "en":
            return "\n\n_SMTP is not configured — use the download link below._"
        return "\n\n_SMTP non configuré — utilisez le lien de téléchargement ci-dessous._"
    if sent:
        if code == "en":
            return f"\n\nThe file was sent to **{email}**. The download link remains available."
        return f"\n\nFichier envoyé à **{email}**. Le lien de téléchargement reste disponible."
    if code == "en":
        return "\n\n_Email delivery failed — use the download link below._"
    return "\n\n_Échec de l'envoi par mail — utilisez le lien de téléchargement ci-dessous._"
