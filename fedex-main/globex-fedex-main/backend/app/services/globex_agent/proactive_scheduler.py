"""Scheduler proactif Globex OS — scan SLA + comptes dormants en arrière-plan."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.activity_log_service import write_log
from app.services.globex_agent.dormant_accounts_service import scan_dormant_accounts
from app.services.globex_agent.ticket_sla_service import scan_sla_breaches
from app.services.notifications_service import _upsert as upsert_platform_notification

logger = logging.getLogger(__name__)

_last_run_at: str | None = None
_last_summary: dict[str, Any] = {}


def get_proactive_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": settings.globex_proactive_enabled,
        "interval_seconds": settings.globex_proactive_interval_seconds,
        "last_run_at": _last_run_at,
        "last_summary": dict(_last_summary),
    }


def run_proactive_scan_cycle(db: Session) -> dict[str, Any]:
    """Un cycle : SLA + dormants → alertes admin plateforme (dédupliquées)."""
    global _last_run_at, _last_summary

    settings = get_settings()
    sla_limit = settings.globex_proactive_sla_limit
    dormant_days = settings.globex_proactive_dormant_days
    dormant_limit = settings.globex_proactive_dormant_limit

    sla_rows = scan_sla_breaches(db, limit=sla_limit)
    dormant_rows = scan_dormant_accounts(db, days=dormant_days, limit=dormant_limit)

    alerts_created = 0
    for row in sla_rows:
        tid = row["ticket_id"]
        key = f"globex-proactive-sla-{tid}"
        upsert_platform_notification(
            db,
            external_key=key,
            category="ia",
            title=f"SLA dépassé — ticket #{tid}",
            message=(
                f"{row.get('subject') or 'Ticket'} — retard {row.get('overdue_hours')}h "
                f"(SLA {row.get('sla_hours')}h, priorité {row.get('priority')})."
            )[:500],
            priority="high" if row.get("priority") in {"high", "urgent", "critical"} else "normal",
            icon="alert-triangle",
            action_type="support_ticket",
            action_ref=str(tid),
        )
        alerts_created += 1

    for row in dormant_rows:
        uid = row["user_id"]
        key = f"globex-proactive-dormant-{uid}"
        name = (row.get("full_name") or row.get("email") or "").strip()
        upsert_platform_notification(
            db,
            external_key=key,
            category="ia",
            title=f"Compte inactif — {name}",
            message=(
                f"{row.get('email')} — aucune activité depuis {row.get('days_inactive')} jours "
                f"(seuil {dormant_days}j)."
            )[:500],
            priority="normal",
            icon="user-x",
            action_type="user",
            action_ref=str(uid),
        )
        alerts_created += 1

    summary = {
        "sla_breaches": len(sla_rows),
        "dormant_accounts": len(dormant_rows),
        "alerts_upserted": alerts_created,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
    _last_run_at = summary["ran_at"]
    _last_summary = summary

    write_log(
        db,
        action="globex_proactive.scan",
        message=(
            f"Scan proactif — SLA {len(sla_rows)}, dormants {len(dormant_rows)}, "
            f"alertes {alerts_created}"
        ),
        category="admin",
        level="INFO",
        commit=False,
    )
    db.commit()
    logger.info("[GlobexProactive] %s", summary)
    return summary


def proactive_scan_loop() -> None:
    """Boucle daemon — intervalle configurable."""
    settings = get_settings()
    interval = max(int(settings.globex_proactive_interval_seconds or 300), 60)
    from app.core.database import SessionLocal

    while True:
        time.sleep(interval)
        if not get_settings().globex_agent_enabled or not get_settings().globex_proactive_enabled:
            continue
        db = SessionLocal()
        try:
            run_proactive_scan_cycle(db)
        except Exception:
            logger.exception("[GlobexProactive] cycle error")
            db.rollback()
        finally:
            db.close()


def run_proactive_scan_once() -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        run_proactive_scan_cycle(db)
    except Exception:
        logger.exception("[GlobexProactive] initial scan error")
        db.rollback()
    finally:
        db.close()
