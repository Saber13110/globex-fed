"""Planification missions agent — datetime, daily/weekly, worker background."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_mission import AgentMission

logger = logging.getLogger(__name__)

_ACTIVE_MISSION_STATUSES = frozenset({"running", "waiting_permission"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_workflow_timing(plan_json: str) -> dict[str, Any] | None:
    if not plan_json or not plan_json.strip():
        return None
    try:
        import json

        data = json.loads(plan_json)
    except json.JSONDecodeError:
        return None
    if data.get("version") != 3 or data.get("type") != "builder":
        return None
    timing = next((n for n in data.get("nodes") or [] if n.get("type") == "timing"), None)
    if not timing:
        return None
    node_data = timing.get("data") or {}
    return {
        "schedule_type": str(node_data.get("scheduleType") or "now"),
        "scheduled_at_raw": node_data.get("scheduledAt"),
        "schedule_time": str(node_data.get("scheduleTime") or "08:00"),
    }


def _parse_iso_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_hh_mm(schedule_time: str) -> tuple[int, int]:
    parts = (schedule_time or "08:00").strip().split(":")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return 8, 0


def _next_daily_run(schedule_time: str, *, after: datetime | None = None) -> datetime:
    ref = after or utc_now()
    hour, minute = _parse_hh_mm(schedule_time)
    candidate = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= ref:
        candidate += timedelta(days=1)
    return candidate


def _next_weekly_run(schedule_time: str, *, after: datetime | None = None) -> datetime:
    ref = after or utc_now()
    daily = _next_daily_run(schedule_time, after=ref)
    if (daily - ref).days < 7 and ref.weekday() == daily.weekday() and daily <= ref:
        return daily + timedelta(days=7)
    if (daily - ref).total_seconds() < 86400 * 6:
        return daily + timedelta(days=6)
    return daily


def compute_next_run_at(
    *,
    schedule_type: str,
    scheduled_at: datetime | None = None,
    schedule_time: str = "08:00",
    now: datetime | None = None,
) -> datetime | None:
    """Prochaine exécution UTC. None = lancement immédiat autorisé."""
    ref = now or utc_now()
    st = (schedule_type or "now").lower()
    if st == "now":
        return None
    if st == "datetime":
        if scheduled_at is None:
            return None
        return scheduled_at if scheduled_at > ref else None
    if st == "daily":
        return _next_daily_run(schedule_time, after=ref)
    if st == "weekly":
        return _next_weekly_run(schedule_time, after=ref)
    return None


def sync_mission_schedule_from_workflow(mission: AgentMission) -> bool:
    """
    Aligne schedule_type / scheduled_at / status depuis le nœud Déclencheur.
    Retourne True si la mission est planifiée (pas immédiate).
    """
    cfg = _parse_workflow_timing(mission.plan_json or "")
    if not cfg:
        return False

    mission.schedule_type = cfg["schedule_type"]
    mission.schedule_time = cfg["schedule_time"]
    explicit_at = _parse_iso_dt(cfg["scheduled_at_raw"])

    if cfg["schedule_type"] == "datetime" and explicit_at:
        mission.scheduled_at = explicit_at
    else:
        next_at = compute_next_run_at(
            schedule_type=cfg["schedule_type"],
            scheduled_at=explicit_at,
            schedule_time=cfg["schedule_time"],
        )
        mission.scheduled_at = next_at

    immediate = cfg["schedule_type"] == "now"
    if immediate:
        if mission.status == "scheduled":
            mission.status = "draft"
        return False

    if mission.status in ("draft", "scheduled", "failed", "waiting_plan_approval"):
        mission.status = "scheduled"
    return True


def is_mission_due(mission: AgentMission, *, now: datetime | None = None) -> bool:
    if mission.status != "scheduled":
        return False
    ref = now or utc_now()
    if not mission.scheduled_at:
        return True
    due_at = mission.scheduled_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    return due_at <= ref


def should_run_immediately(mission: AgentMission) -> bool:
    cfg = _parse_workflow_timing(mission.plan_json or "")
    if not cfg:
        return mission.schedule_type == "now"
    return cfg["schedule_type"] == "now"


def admin_has_active_mission(
    db: Session,
    admin_id: int,
    *,
    exclude_mission_id: int | None = None,
) -> AgentMission | None:
    q = select(AgentMission).where(
        AgentMission.admin_id == admin_id,
        AgentMission.status.in_(tuple(_ACTIVE_MISSION_STATUSES)),
    )
    if exclude_mission_id:
        q = q.where(AgentMission.id != exclude_mission_id)
    return db.scalar(q)


def schedule_recurring_after_complete(mission: AgentMission) -> bool:
    """Replanifie daily/weekly après succès. Retourne True si replanifiée."""
    st = (mission.schedule_type or "now").lower()
    if st not in ("daily", "weekly"):
        return False
    if st == "daily":
        mission.scheduled_at = _next_daily_run(mission.schedule_time or "08:00", after=utc_now())
    else:
        mission.scheduled_at = _next_weekly_run(mission.schedule_time or "08:00", after=utc_now())
    mission.status = "scheduled"
    mission.started_at = None
    return True


def process_scheduled_missions(db: Session) -> int:
    """Lance les missions planifiées arrivées à échéance. Retourne le nombre démarrées."""
    from app.services.agent_mission_service import run_mission

    now = utc_now()
    rows = list(
        db.scalars(
            select(AgentMission)
            .where(AgentMission.status == "scheduled")
            .order_by(AgentMission.scheduled_at.asc().nullsfirst())
            .limit(20)
        ).all()
    )
    started = 0
    for mission in rows:
        if not is_mission_due(mission, now=now):
            continue
        if admin_has_active_mission(db, mission.admin_id, exclude_mission_id=mission.id):
            logger.info(
                "Mission #%s due but admin #%s already has active mission — skip",
                mission.id,
                mission.admin_id,
            )
            continue
        try:
            run_mission(db, mission.id)
            started += 1
            logger.info("Mission planifiée #%s lancée par le scheduler", mission.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Échec lancement mission planifiée #%s: %s", mission.id, exc)
            db.rollback()
    return started


def completed_step_orders(mission: AgentMission) -> set[int]:
    return {
        int(s.step_order)
        for s in (mission.steps or [])
        if s.status in ("completed", "waiting_approval")
    }


def last_completed_summary(mission: AgentMission) -> str:
    import json

    done = [s for s in (mission.steps or []) if s.status == "completed" and s.output_json]
    if not done:
        return ""
    last = max(done, key=lambda s: s.step_order)
    try:
        data = json.loads(last.output_json or "{}")
    except json.JSONDecodeError:
        return ""
    return str(data.get("task_answer") or data.get("analysis") or "")
