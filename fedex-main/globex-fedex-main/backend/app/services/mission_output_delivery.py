"""Livraison des résultats mission — panel / notification / e-mail."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_mission import AgentMission
from app.models.user import User, UserRole, UserStatus
from app.services.email_service import is_email_configured, send_email
from app.services.mission_task_catalog import AGENT_LABELS, normalize_agent_type
from app.services.notifications_service import _upsert as upsert_platform_notification

logger = logging.getLogger(__name__)

VALID_DESTINATIONS = frozenset({"results_panel", "admin_notification", "email"})


def _admin_recipient_emails(db: Session, mission: AgentMission) -> list[str]:
    emails: list[str] = []
    if mission.admin_id:
        admin = db.get(User, mission.admin_id)
        if admin and admin.email:
            emails.append(admin.email.strip().lower())
    if not emails:
        rows = db.scalars(
            select(User.email).where(
                User.role == UserRole.admin.value,
                User.status == UserStatus.active.value,
            )
        ).all()
        emails = [str(e).strip().lower() for e in rows if e]
    return list(dict.fromkeys(emails))


def deliver_mission_outputs(
    db: Session,
    mission: AgentMission,
    *,
    summary: str,
    destinations: list[str] | None,
    step_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Applique les destinations du bloc Résultat (hors notify_on_complete lifecycle).
    results_panel : résultats déjà persistés — noop.
    """
    dests = [d for d in (destinations or ["results_panel"]) if d in VALID_DESTINATIONS]
    if not dests:
        dests = ["results_panel"]

    report: dict[str, Any] = {"destinations": dests, "delivered": []}
    body = (summary or mission.task_description or "")[:2000]
    canonical = normalize_agent_type(mission.agent_type)
    label = AGENT_LABELS.get(canonical, mission.agent_type)

    for dest in dests:
        if dest == "results_panel":
            report["delivered"].append({"destination": dest, "ok": True, "note": "stored"})
            continue

        if dest == "admin_notification":
            upsert_platform_notification(
                db,
                external_key=f"agent-mission-{mission.id}-output",
                category="agent_mission",
                title=f"Résultat mission — {label}",
                message=body[:500],
                route=f"/admin/agent-missions/{mission.id}?tab=results",
                icon="file-text",
                action_label="Voir résultats",
                action_type="agent_mission",
                action_ref=str(mission.id),
                priority="normal",
            )
            report["delivered"].append({"destination": dest, "ok": True})
            continue

        if dest == "email":
            if not is_email_configured():
                report["delivered"].append(
                    {"destination": dest, "ok": False, "error": "smtp_not_configured"}
                )
                continue
            recipients = _admin_recipient_emails(db, mission)
            if not recipients:
                report["delivered"].append(
                    {"destination": dest, "ok": False, "error": "no_recipient"}
                )
                continue
            subject = f"[Globex] Résultat mission {label} #{mission.id}"
            sent = 0
            for to in recipients:
                try:
                    if send_email(to=to, subject=subject, body_text=body):
                        sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Mission #%s email to %s failed: %s", mission.id, to, exc)
            report["delivered"].append(
                {
                    "destination": dest,
                    "ok": sent > 0,
                    "recipients": sent,
                }
            )

    if step_outputs:
        report["step_count"] = len(step_outputs)
    return report
