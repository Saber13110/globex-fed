"""Scheduler — envoi automatique des rapports quotidien client."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_daily_report_settings import UserDailyReportSettings
from app.services.client_phase8.daily_report_executor import execute_send_daily_report
from app.services.client_phase8.daily_report_preferences import local_now, mark_sent_today

logger = logging.getLogger(__name__)


def process_scheduled_daily_reports(db: Session) -> int:
    """Envoie les rapports planifiés dont l'heure locale correspond. Retourne le nombre d'envois."""
    rows = list(
        db.scalars(
            select(UserDailyReportSettings).where(UserDailyReportSettings.enabled.is_(True))
        ).all()
    )
    sent_count = 0
    for settings in rows:
        user = db.get(User, settings.user_id)
        if user is None or not (user.email or "").strip():
            continue
        now_local = local_now()
        today: date = now_local.date()
        if settings.last_sent_local_date == today:
            continue
        run_time = (settings.run_time or "18:00").strip()
        parts = run_time.split(":")
        try:
            target_h = int(parts[0])
            target_m = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            target_h, target_m = 18, 0
        if now_local.hour != target_h or now_local.minute != target_m:
            continue
        lang = (user.preferred_language or "fr").lower()[:2]
        if lang not in {"fr", "en"}:
            lang = "fr"
        ok, _, _ = execute_send_daily_report(
            db,
            user,
            lang=lang,
            use_llm_narrative=True,
        )
        if ok:
            mark_sent_today(db, settings.user_id, local_date=today)
            sent_count += 1
            logger.info("Rapport quotidien planifié envoyé user_id=%s", settings.user_id)
    return sent_count
