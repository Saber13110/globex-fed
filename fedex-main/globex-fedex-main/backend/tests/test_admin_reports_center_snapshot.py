"""Tests snapshot Centre de rapports — parité UI."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.report_run import ReportRun
from app.services.admin_client.reports.reports_center_snapshot import (
    get_reports_center_snapshot,
    resolve_target_run,
)
from app.services.admin_client.reports.reports_types import ReportsPlan, ReportsProfile, ReportsTaskType
from app.services.reports_service import REPORTS_DIR


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


def test_snapshot_file_available_stale_path(db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.reports_service.REPORTS_DIR", tmp_path)
    canonical = tmp_path / "report_1_tracking-history.xlsx"
    canonical.write_bytes(b"xlsx")
    run = ReportRun(
        slug="tracking-history",
        name="Tracking History",
        category="shipments",
        format="xlsx",
        period_label="week",
        status="completed",
        file_path=r"C:\old\path\report_1_tracking-history.xlsx",
        row_count=1,
    )
    db.add(run)
    db.commit()

    snap = get_reports_center_snapshot(db, limit=5)
    assert snap["recent_runs"][0]["id"] == 1
    assert snap["file_available"][1] is True
    assert any(c.get("slug") == "tracking-history" for c in snap["catalog"])


def test_resolve_via_catalog_last_run_id(db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.reports_service.REPORTS_DIR", tmp_path)
    path = tmp_path / "report_2_financial-summary.xlsx"
    path.write_bytes(b"xlsx")
    run = ReportRun(
        slug="financial-summary",
        name="Financial Summary",
        category="finance",
        format="xlsx",
        period_label="week",
        status="completed",
        file_path=str(path),
        row_count=2,
    )
    db.add(run)
    db.commit()

    snap = get_reports_center_snapshot(db, limit=5)
    plan = ReportsPlan(
        task_type=ReportsTaskType.report_preview,
        slug_hint="financial-summary",
        profile=ReportsProfile.PREVIEW,
    )
    chosen = resolve_target_run(db, plan, snap, require_file=True)
    assert chosen["slug"] == "financial-summary"
    assert chosen["id"] == run.id
