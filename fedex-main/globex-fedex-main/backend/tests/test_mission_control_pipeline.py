"""Tests pipeline Mission Control admin — classification, compose, actions."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.chat_session import ChatSession
from app.models.user import User
from app.schemas.agent_missions import (
    AgentMissionListItem,
    AgentMissionListResponse,
    AgentMissionResults,
    AgentStepResultRead,
)
from app.services.admin_client.intent_priority import should_route_logs, should_route_missions
from app.services.admin_client.missions.missions_compose import compose_missions_response
from app.services.admin_client.missions.missions_followup import (
    extract_mission_ref,
    wants_last_failed_mission,
)
from app.services.admin_client.missions.missions_intent import classify_missions_intent
from app.services.admin_client.missions.missions_pending import (
    build_missions_pending_marker,
    is_missions_delete_phrase,
    parse_pending_mission_action,
)
from app.services.admin_client.missions.missions_state import (
    validate_cancel,
    validate_delete,
    validate_retry,
)
from app.services.admin_client.missions.missions_types import MissionsPlan, MissionsProfile, MissionsTaskType
from app.services.admin_client.missions.missions_executor import try_admin_missions_turn


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
        email="admin-missions@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-missions",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Missions test")
    db.add(sess)
    db.flush()
    return sess


def test_classify_mission_list_failed_filter():
    plan = classify_missions_intent("lister les missions échouées")
    assert plan.task_type == MissionsTaskType.mission_list
    assert plan.status_filter == "failed"


def test_classify_mission_results_hash():
    plan = classify_missions_intent("résultats mission #521")
    assert plan.task_type == MissionsTaskType.mission_results
    assert plan.mission_id == 521


def test_classify_mission_logs_summary():
    plan = classify_missions_intent("résumer logs mission 521")
    assert plan.task_type == MissionsTaskType.mission_logs_summary
    assert plan.mission_id == 521


def test_extract_mission_ref_from_history():
    hist = "**Missions agent**\n- #521 | Support | failed | test"
    assert extract_mission_ref("#521", history_text=hist) == 521


def test_wants_last_failed_mission():
    assert wants_last_failed_mission("dernière mission échouée") is True


def test_should_route_missions_not_platform_logs():
    assert should_route_logs("résumer logs mission #521") is False
    assert should_route_missions("résumer logs mission #521") is True
    assert should_route_missions("lister les missions agent") is True
    assert should_route_missions("liste moi les missions agents") is True
    assert should_route_missions("liste moi les mission echoue") is True


def test_classify_user_phrases():
    plan = classify_missions_intent("liste moi les missions agents")
    assert plan.task_type == MissionsTaskType.mission_list
    plan2 = classify_missions_intent("liste moi les mission echoue")
    assert plan2.task_type == MissionsTaskType.mission_list
    assert plan2.status_filter == "failed"


def test_state_machine_retry_failed():
    assert validate_retry("failed") is None
    assert validate_retry("paused") is not None


def test_state_machine_delete_allowed():
    assert validate_delete("draft") is None
    assert validate_delete("running") is not None


def test_state_machine_cancel_completed():
    assert validate_cancel("completed") is not None
    assert validate_cancel("running") is None


def test_compose_list():
    processed = {
        "items": [
            {
                "id": 521,
                "agent_type": "support",
                "status": "failed",
                "task_description": "Ticket amine",
            }
        ],
        "stats": {"total": 1, "running": 0, "completed": 0},
        "status_filter": "failed",
    }
    plan = MissionsPlan(task_type=MissionsTaskType.mission_list, profile=MissionsProfile.LIST)
    text = compose_missions_response(processed, plan, lang="fr")
    assert "Missions agent" in text
    assert "#521" in text
    assert "/admin/agent-missions/521" in text


def test_compose_logs_summary():
    processed = {
        "mission": {"id": 521, "agent_type": "support", "status": "failed"},
        "logs_summary": {
            "counts": {"INFO": 3, "WARNING": 1, "ERROR": 2},
            "recent_issues": [{"level": "ERROR", "at": "2026-01-01", "message": "handoff mismatch"}],
            "timeline": [{"step_order": 1, "status": "completed", "excerpt": "ok"}],
        },
    }
    plan = MissionsPlan(
        task_type=MissionsTaskType.mission_logs_summary,
        profile=MissionsProfile.LOGS,
        mission_id=521,
    )
    text = compose_missions_response(processed, plan, lang="fr")
    assert "Logs mission #521" in text
    assert "ERROR 2" in text
    assert "tab=logs" in text


def test_pending_marker_parse_and_delete_phrase():
    marker = build_missions_pending_marker(
        "delete",
        521,
        stage="delete_phrase",
        expected_phrase="SUPPRIMER mission #521",
    )
    pending = parse_pending_mission_action(f"Confirmez{marker}")
    assert pending is not None
    assert pending.mission_id == 521
    assert pending.stage == "delete_phrase"
    assert is_missions_delete_phrase("SUPPRIMER mission #521", pending.expected_phrase)


@patch("app.services.admin_client.missions.missions_pipeline.mission_svc.list_missions_filtered")
def test_pipeline_list_metadata(mock_list, db, admin, chat_session):
    now = datetime.now(timezone.utc)
    mock_list.return_value = AgentMissionListResponse(
        items=[
            AgentMissionListItem(
                id=521,
                agent_type="support",
                task_description="Workflow test",
                status="failed",
                schedule_type="immediate",
                scheduled_at=None,
                created_at=now,
                started_at=now,
                finished_at=now,
            )
        ],
        total=1,
        stats={"total": 1, "running": 0, "completed": 0, "failed": 1},
    )
    out = try_admin_missions_turn(db, admin, chat_session, "lister les missions échouées", 1, "fr")
    assert out is not None
    assert out["tool_called"] is True
    assert out["data_source"] == "admin_agent_missions"
    assert out["intent"] == "missions_list"
    assert "#521" in out["reply"]
    assert "failed" in out["reply"]


@patch("app.services.admin_client.missions.missions_pipeline.mission_svc.get_mission")
@patch("app.services.admin_client.missions.missions_pipeline.mission_svc.summarize_mission_logs")
def test_pipeline_logs_summary(mock_summary, mock_get, db, admin, chat_session):
    mock_get.return_value = MagicMock(
        model_dump=lambda: {
            "id": 521,
            "agent_type": "support",
            "task_description": "test",
            "status": "failed",
            "results": AgentMissionResults(
                has_results=False,
                executive_summary="",
                metrics={},
                step_results=[],
            ).model_dump(),
        }
    )
    mock_summary.return_value = {
        "counts": {"INFO": 1, "WARNING": 0, "ERROR": 1},
        "recent_issues": [],
        "timeline": [],
        "link": "/admin/agent-missions/521?tab=logs",
    }
    out = try_admin_missions_turn(
        db, admin, chat_session, "résumer logs mission #521", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "missions_logs_summary"
    assert "Logs mission #521" in out["reply"]


@patch("app.services.admin_client.missions.missions_pipeline.mission_svc.run_mission")
@patch("app.services.admin_client.missions.missions_pipeline.mission_svc.get_mission")
def test_pipeline_retry_failed(mock_get, mock_run, db, admin, chat_session):
    mock_get.return_value = MagicMock(
        model_dump=lambda: {
            "id": 521,
            "agent_type": "support",
            "task_description": "test",
            "status": "failed",
            "results": {},
        }
    )
    mock_run.return_value = MagicMock(
        model_dump=lambda: {"id": 521, "status": "running", "agent_type": "support"}
    )
    out = try_admin_missions_turn(db, admin, chat_session, "relancer mission #521", 1, "fr")
    assert out is not None
    assert out["intent"] == "missions_retry"
    mock_run.assert_called_once_with(db, 521)


def test_summarize_mission_logs_service(db):
    from app.models.agent_execution_log import AgentExecutionLog
    from app.models.agent_mission import AgentMission
    from app.services import agent_mission_service as svc

    mission = AgentMission(
        admin_id=1,
        agent_type="support",
        task_description="test logs",
        status="failed",
        schedule_type="immediate",
    )
    db.add(mission)
    db.flush()
    db.add(
        AgentExecutionLog(
            mission_id=mission.id,
            level="ERROR",
            message="Échec handoff",
            details_json="{}",
        )
    )
    db.commit()

    summary = svc.summarize_mission_logs(db, mission.id)
    assert summary["counts"]["ERROR"] == 1
    assert summary["link"].endswith("?tab=logs")
