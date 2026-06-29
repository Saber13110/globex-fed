"""Tests pipeline reports admin."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.admin_client.reports.reports_executor import try_admin_reports_turn
from app.services.admin_client.reports.reports_types import ReportsToolError


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
        email="admin@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-admin-1",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Test")
    db.add(sess)
    db.flush()
    return sess


@patch("app.services.admin_client.reports.reports_tool.fetch_reports_center")
def test_pipeline_list_recent_metadata(mock_fetch, db, admin, chat_session):
    now = datetime.now(timezone.utc).isoformat()
    mock_fetch.return_value = {
        "catalog": [],
        "file_available": {5: True},
        "recent_runs": [
            {
                "id": 5,
                "slug": "tracking-history",
                "name": "Tracking History",
                "format": "xlsx",
                "status": "completed",
                "file_size": 1200,
                "row_count": 42,
                "created_at": now,
                "download_url": "/api/reports/runs/5/download",
            }
        ],
    }
    out = try_admin_reports_turn(
        db, admin, chat_session, "Montre les exports récents", 1, "fr"
    )
    assert out is not None
    assert out["tool_called"] is True
    assert out["data_source"] == "admin_reports_api"
    assert out["raw_data_received"] is True
    assert "Tracking History" in out["reply"]
    assert "Source : Centre de rapports Admin" in out["reply"]


@patch("app.services.admin_client.reports.reports_tool.fetch_reports_center")
def test_pipeline_fetch_failure(mock_fetch, db, admin, chat_session):
    mock_fetch.side_effect = ReportsToolError("db down")
    out = try_admin_reports_turn(
        db, admin, chat_session, "Prévisualise le dernier export", 1, "fr"
    )
    assert out is not None
    assert out["raw_data_received"] is False


@patch("app.services.admin_client.reports.reports_tool.fetch_reports_center")
def test_pipeline_file_missing_lists_runs(mock_fetch, db, admin, chat_session):
    now = datetime.now(timezone.utc).isoformat()
    mock_fetch.return_value = {
        "catalog": [],
        "file_available": {3: False},
        "recent_runs": [
            {
                "id": 3,
                "slug": "tracking-history",
                "name": "Tracking History",
                "format": "xlsx",
                "status": "completed",
                "file_size": 0,
                "row_count": 10,
                "created_at": now,
                "download_url": "/api/reports/runs/3/download",
            }
        ],
    }
    with patch(
        "app.services.admin_client.reports.reports_pipeline.resolve_target_run",
        return_value={
            "id": 3,
            "name": "Tracking History",
            "format": "xlsx",
            "status": "completed",
            "row_count": 10,
            "download_url": "/api/reports/runs/3/download",
        },
    ), patch(
        "app.services.admin_client.reports.reports_tool.preview_report",
        side_effect=ReportsToolError("preview_failed"),
    ):
        out = try_admin_reports_turn(
            db, admin, chat_session, "Prévisualise le dernier rapport", 1, "fr"
        )
    assert out is not None
    assert out["raw_data_received"] is True
    assert "Tracking History" in out["reply"]
    assert "régénérez" in out["reply"].lower()


@patch("app.services.admin_client.reports.reports_tool.search_users_for_reports")
@patch("app.services.admin_client.reports.reports_pipeline.resolve_target_run")
@patch("app.services.admin_client.reports.reports_tool.fetch_reports_center")
def test_pipeline_share_prompt_without_file(
    mock_fetch, mock_resolve, mock_users, db, admin, chat_session
):
    mock_fetch.return_value = {
        "catalog": [],
        "file_available": {1: False},
        "recent_runs": [{"id": 1, "format": "xlsx", "name": "Fin", "status": "completed"}],
    }
    mock_resolve.return_value = {
        "id": 1,
        "name": "Financial Summary",
        "format": "xlsx",
        "status": "completed",
        "row_count": 2,
        "download_url": "/api/reports/runs/1/download",
    }
    mock_users.return_value = [
        {"id": 9, "email": "sxr2123@gmail.com", "full_name": "Bob", "status": "active"}
    ]
    out = try_admin_reports_turn(
        db,
        admin,
        chat_session,
        "Partage le rapport 1 a sxr2123@gmail.com",
        1,
        "fr",
    )
    assert out is not None
    assert out["raw_data_received"] is True
    assert "Confirmation de partage" in out["reply"]
    assert "sxr2123@gmail.com" in out["reply"]
