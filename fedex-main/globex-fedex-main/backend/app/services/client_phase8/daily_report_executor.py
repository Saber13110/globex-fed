"""Orchestration génération + envoi rapport quotidien."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.client_phase8.daily_report_charts import render_daily_report_charts
from app.services.client_phase8.daily_report_collector import DailyReportSnapshot, collect_daily_report
from app.services.client_phase8.daily_report_email import send_daily_report_email
from app.services.client_phase8.daily_report_narrative import (
    factual_daily_report_narrative,
    generate_daily_report_narrative,
)
from app.services.client_phase8.daily_report_pdf import generate_daily_report_pdf
from app.services.email_service import is_email_configured

logger = logging.getLogger(__name__)


def build_daily_report_bundle(
    db: Session,
    user: User,
    *,
    lang: str,
    use_llm_narrative: bool = False,
) -> tuple[DailyReportSnapshot, str, bytes, str]:
    snapshot = collect_daily_report(db, user, lang=lang)
    if use_llm_narrative:
        narrative = generate_daily_report_narrative(snapshot)
    else:
        narrative = factual_daily_report_narrative(snapshot)
    try:
        charts = render_daily_report_charts(snapshot)
    except Exception:
        logger.warning("matplotlib indisponible — PDF sans graphiques", exc_info=True)
        charts = {}
    pdf_bytes, filename = generate_daily_report_pdf(snapshot, narrative=narrative, chart_pngs=charts)
    return snapshot, narrative, pdf_bytes, filename


def execute_send_daily_report(
    db: Session,
    user: User,
    *,
    lang: str,
    use_llm_narrative: bool = False,
) -> tuple[bool, str, DailyReportSnapshot | None]:
    if not (user.email or "").strip():
        if lang == "en":
            return False, "Add an email address to your account to receive the daily report.", None
        return False, "Ajoutez une adresse e-mail à votre compte pour recevoir le rapport.", None
    if not is_email_configured():
        if lang == "en":
            return False, "SMTP is not configured — the daily report cannot be sent by email.", None
        return False, "SMTP non configuré — le rapport ne peut pas être envoyé par mail.", None

    snapshot, narrative, pdf_bytes, filename = build_daily_report_bundle(
        db, user, lang=lang, use_llm_narrative=use_llm_narrative
    )
    sent = send_daily_report_email(user, snapshot, narrative=narrative, pdf_bytes=pdf_bytes, filename=filename)
    if not sent:
        if lang == "en":
            return False, "Email delivery failed. Please try again later.", snapshot
        return False, "Échec de l'envoi par mail. Réessayez plus tard.", snapshot

    k = snapshot.kpi_dict()
    if lang == "en":
        msg = (
            f"Your daily activity report was sent to **{user.email}**.\n\n"
            f"Summary: {k['messages']} message(s), {k['trackings']} shipment(s), "
            f"{k['exports']} export(s), **{k['unread_notifications']} unread notification(s)**."
        )
    else:
        msg = (
            f"Votre rapport d'activité a été envoyé à **{user.email}**.\n\n"
            f"Résumé : {k['messages']} message(s), {k['trackings']} colis, "
            f"{k['exports']} export(s), **{k['unread_notifications']} notification(s) non lue(s)**."
        )
    return True, msg, snapshot
