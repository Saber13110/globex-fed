"""Tests — planification missions M3."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.agent_mission import AgentMission
from app.models.user import User
from app.services.mission_scheduler import (
    admin_has_active_mission,
    compute_next_run_at,
    is_mission_due,
    should_run_immediately,
    sync_mission_schedule_from_workflow,
    utc_now,
)


def _wf(**timing_data) -> str:
    return json.dumps(
        {
            "version": 3,
            "type": "builder",
            "nodes": [
                {"id": "t1", "type": "timing", "data": timing_data},
                {"id": "a1", "type": "agent", "data": {"agentType": "users"}},
            ],
            "edges": [],
        }
    )


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin(db):
    user = User(
        email="admin-sched@test.com",
        password_hash="x",
        full_name="Admin Sched",
        role="admin",
        status="active",
        organization_id="org-sched",
    )
    db.add(user)
    db.flush()
    return user


def test_compute_next_run_at_now_immediate():
    ref = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    nxt = compute_next_run_at(schedule_type="now", now=ref)
    assert nxt is None


def test_sync_mission_schedule_ignores_delay(db, admin):
    mission = AgentMission(
        admin_id=admin.id,
        agent_type="users",
        task_description="test",
        status="draft",
        schedule_type="now",
        plan_json=_wf(label="Lancement", scheduleType="now", delayMinutes=30),
    )
    db.add(mission)
    db.flush()
    assert sync_mission_schedule_from_workflow(mission) is False
    assert mission.status == "draft"
    assert mission.scheduled_at is None


def test_should_run_immediately_no_delay():
    mission = AgentMission(
        admin_id=1,
        agent_type="users",
        task_description="x",
        status="draft",
        schedule_type="now",
        plan_json=_wf(scheduleType="now", delayMinutes=0),
    )
    assert should_run_immediately(mission) is True


def test_is_mission_due():
    mission = AgentMission(
        admin_id=1,
        agent_type="users",
        task_description="x",
        status="scheduled",
        schedule_type="datetime",
        scheduled_at=utc_now() - timedelta(minutes=1),
    )
    assert is_mission_due(mission) is True


def test_admin_has_active_mission(db, admin):
    m1 = AgentMission(
        admin_id=admin.id,
        agent_type="users",
        task_description="a",
        status="running",
        schedule_type="now",
    )
    db.add(m1)
    db.flush()
    assert admin_has_active_mission(db, admin.id) is not None


@patch("app.services.agent_mission_service.run_mission")
def test_process_scheduled_missions_starts_due(mock_run, db, admin):
    from app.services.mission_scheduler import process_scheduled_missions

    mission = AgentMission(
        admin_id=admin.id,
        agent_type="users",
        task_description="list",
        status="scheduled",
        schedule_type="now",
        scheduled_at=utc_now() - timedelta(seconds=5),
        plan_json="[]",
    )
    db.add(mission)
    db.commit()
    count = process_scheduled_missions(db)
    assert count == 1
    mock_run.assert_called_once_with(db, mission.id)
