"""Service d'envoi d'emails via SMTP (Gmail).

Utilise la bibliothèque standard `smtplib` (aucune dépendance externe).
Si le SMTP n'est pas configuré, l'envoi est ignoré proprement (retourne False).
"""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings


def is_email_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from)


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Envoie un email. Lève une exception en cas d'échec SMTP réel.

    Retourne False (sans lever) uniquement si le service n'est pas configuré.
    """
    settings = get_settings()
    if not is_email_configured():
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    if settings.smtp_use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)

    return True


def send_email_with_attachment(
    to: str,
    subject: str,
    body_text: str,
    *,
    attachment_bytes: bytes,
    attachment_filename: str,
    attachment_mime: str = "application/pdf",
    body_html: str | None = None,
) -> bool:
    """Envoie un e-mail avec une pièce jointe (PDF, etc.)."""
    settings = get_settings()
    if not is_email_configured():
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")
    message.add_attachment(
        attachment_bytes,
        maintype=attachment_mime.split("/")[0],
        subtype=attachment_mime.split("/")[-1],
        filename=attachment_filename,
    )

    if settings.smtp_use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)

    return True
