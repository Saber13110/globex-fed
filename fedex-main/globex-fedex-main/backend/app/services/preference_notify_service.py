"""Notifications email aux administrateurs (soumissions de préférences)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.preference_submission import PreferenceSubmission
from app.models.user import User, UserRole, UserStatus
from app.services.email_service import is_email_configured, send_email

logger = logging.getLogger(__name__)


def _admin_recipients(db: Session) -> list[str]:
    settings = get_settings()
    extra = (getattr(settings, "admin_notify_email", None) or "").strip()
    if extra:
        return [extra]
    rows = db.scalars(
        select(User.email).where(
            User.role == UserRole.admin.value,
            User.status == UserStatus.active.value,
        )
    ).all()
    emails = [str(e).strip().lower() for e in rows if e]
    if not emails and settings.admin_email:
        emails = [settings.admin_email.strip().lower()]
    return list(dict.fromkeys(emails))


def notify_admins_preference_submitted(
    db: Session,
    *,
    submission: PreferenceSubmission,
    user: User,
) -> bool:
    """Envoie un email aux admins. Ne lève pas si SMTP indisponible."""
    settings = get_settings()
    if not settings.notify_admin_on_preference_submit:
        return False
    if not is_email_configured():
        logger.debug("Notification préférences ignorée : SMTP non configuré.")
        return False

    recipients = _admin_recipients(db)
    if not recipients:
        logger.debug("Notification préférences ignorée : aucun email admin.")
        return False

    base = settings.frontend_base_url.rstrip("/")
    admin_url = f"{base}/admin"
    preview = (submission.proposed_text or "")[:400]
    if len(submission.proposed_text or "") > 400:
        preview += "…"

    subject = f"[Globex FedEx] Préférences IA à valider — {user.full_name}"
    body_text = (
        f"Bonjour,\n\n"
        f"{user.full_name} ({user.email}) a soumis de nouvelles préférences IA.\n\n"
        f"Score de risque : {submission.risk_score}\n"
        f"ID soumission : {submission.id}\n\n"
        f"Aperçu :\n{preview}\n\n"
        f"Validez dans l'administration : {admin_url}\n"
        f"(onglet « Préférences à valider »)\n\n"
        f"— Globex FedEx Chatbot"
    )
    body_html = (
        f"<p>Bonjour,</p>"
        f"<p><strong>{user.full_name}</strong> ({user.email}) a soumis de nouvelles préférences IA.</p>"
        f"<p>Score de risque : <strong>{submission.risk_score}</strong> · "
        f"Soumission #{submission.id}</p>"
        f"<pre style='white-space:pre-wrap;font-family:inherit'>{preview}</pre>"
        f'<p><a href="{admin_url}">Ouvrir l\'administration</a> (onglet Préférences à valider)</p>'
    )

    sent_any = False
    for to in recipients:
        try:
            if send_email(to=to, subject=subject, body_text=body_text, body_html=body_html):
                sent_any = True
        except Exception as exc:  # noqa: BLE001
            logger.exception("Échec email notification préférences vers %s : %s", to, exc)
    return sent_any
