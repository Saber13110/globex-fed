"""Tests E2E agent Reports — fichiers réels, parité Centre de rapports."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.chat_session import ChatSession
from app.models.report_run import ReportRun
from app.models.user import User
from app.services.admin_client.intent_priority import should_route_dashboard, should_route_reports
from app.services.admin_client.reports.reports_executor import try_admin_reports_turn


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


@pytest.fixture()
def seeded_runs(db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.reports_service.REPORTS_DIR", tmp_path)

    json_path = tmp_path / "report_6_exception-report.json"
    json_path.write_text("[]", encoding="utf-8")
    xlsx_path = tmp_path / "report_4_tracking-history.xlsx"
    wb = __import__("openpyxl").Workbook()
    wb.active.append(["id", "status"])
    wb.active.append(["1", "ok"])
    wb.save(xlsx_path)
    wb.close()
    fin_path = tmp_path / "report_1_financial-summary.xlsx"
    fin_path.write_bytes(b"xlsx")

    specs = [
        (6, "exception-report", "Exception Report", "json", str(json_path), 0),
        (4, "tracking-history", "Tracking History", "xlsx", str(xlsx_path), 1),
        (1, "financial-summary", "Financial Summary", "xlsx", str(fin_path), 2),
    ]
    for rid, slug, name, fmt, fpath, rows in specs:
        db.add(
            ReportRun(
                id=rid,
                slug=slug,
                name=name,
                category="shipments",
                format=fmt,
                period_label="week",
                status="completed",
                file_path=fpath,
                row_count=rows,
            )
        )
    db.commit()
    return specs


def test_e2e_preview_latest(db, admin, chat_session, seeded_runs):
    out = try_admin_reports_turn(
        db, admin, chat_session, "Prévisualise le dernier rapport exporté", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "reports_preview"
    assert out["raw_data_received"] is True
    assert "Aperçu" in out["reply"] or "Exception" in out["reply"]


def test_e2e_list_recent(db, admin, chat_session, seeded_runs):
    out = try_admin_reports_turn(db, admin, chat_session, "Montre les exports récents", 1, "fr")
    assert out is not None
    assert out["intent"] == "reports_list"
    assert "Tracking History" in out["reply"]
    assert "Centre de rapports Admin" in out["reply"]


def test_e2e_redownload_excel(db, admin, chat_session, seeded_runs):
    out = try_admin_reports_turn(
        db, admin, chat_session, "Re-télécharge le dernier export Excel", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "reports_download"
    assert out["export_download"] is not None
    assert out["export_download"]["format"] == "xlsx"
    assert out["export_download"]["run_id"] == 4


def test_e2e_share_prompt(db, admin, chat_session, seeded_runs):
    db.add(
        User(
            email="sxr2123@gmail.com",
            password_hash="x",
            full_name="Bob",
            role="client",
            status="active",
            organization_id="org-1",
        )
    )
    db.commit()
    out = try_admin_reports_turn(
        db,
        admin,
        chat_session,
        "Partage le rapport 1 a sxr2123@gmail.com",
        1,
        "fr",
    )
    assert out is not None
    assert out["intent"] == "reports_share"
    assert "Confirmation" in out["reply"]
    assert "sxr2123@gmail.com" in out["reply"]


@patch("app.services.admin_client.reports.reports_tool.share_report_email")
def test_e2e_share_confirm(mock_share, db, admin, chat_session, seeded_runs):
    mock_share.return_value = {
        "run_name": "Financial Summary",
        "sent_to": ["sxr2123@gmail.com"],
        "failures": [],
        "skipped_unknown_or_inactive": [],
        "smtp_ok": True,
    }
    history = [
        {
            "role": "assistant",
            "content": 'Confirmez [REPORTS_SHARE_PENDING {"run_id": 1, "recipients": ["sxr2123@gmail.com"]}]',
        }
    ]
    out = try_admin_reports_turn(
        db,
        admin,
        chat_session,
        "oui",
        2,
        "fr",
        history_text=history[0]["content"],
        conversation_history=history,
    )
    assert out is not None
    assert out["intent"] == "reports_share_done"
    mock_share.assert_called_once()


def test_e2e_list_all_reports(db, admin, chat_session, seeded_runs):
    out = try_admin_reports_turn(db, admin, chat_session, "liste moi tous les reports", 1, "fr")
    assert out is not None
    assert out["intent"] == "reports_list"
    assert "Tracking History" in out["reply"]


def test_e2e_non_regression_routing():
    assert should_route_reports("suivi 817725683025") is False
    assert should_route_dashboard("rapport des retards pdf") is True
