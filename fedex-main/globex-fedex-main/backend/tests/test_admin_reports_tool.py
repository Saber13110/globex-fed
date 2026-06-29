"""Tests outils reports admin."""

from __future__ import annotations

from unittest.mock import patch

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
from app.services.admin_client.reports.reports_processors import validate_report_data
from app.services.admin_client.reports.reports_tool import list_recent_report_runs, preview_report
from app.services.admin_client.reports.reports_types import ReportsPlan, ReportsProfile, ReportsTaskType


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


def test_validate_report_data_ok():
    result = validate_report_data({"status": "completed", "file_path": "/x", "download_url": "/d"})
    assert result["valid"] is True


def test_validate_report_data_complet_status():
    result = validate_report_data({"status": "complet", "file_path": "/x", "download_url": "/d"})
    assert result["valid"] is True


@patch("app.services.admin_client.reports.reports_tool.fetch_reports_center")
def test_list_recent_report_runs(mock_fetch, db):
    mock_fetch.return_value = {
        "recent_runs": [
            {
                "id": 1,
                "slug": "tracking-history",
                "name": "Tracking",
                "format": "json",
                "status": "completed",
                "row_count": 2,
                "download_url": "/api/reports/runs/1/download",
            }
        ],
        "catalog": [],
        "file_available": {1: True},
    }
    rows = list_recent_report_runs(db, limit=5)
    assert len(rows) == 1
    assert rows[0]["id"] == 1


@patch("app.services.admin_client.reports.reports_tool.get_run_download")
@patch("app.services.admin_client.reports.reports_tool.preview_run")
def test_preview_report(mock_preview, mock_download, db):
    from app.schemas.reports import ReportPreviewResponse

    run = ReportRun(
        slug="t",
        name="T",
        category="shipments",
        format="json",
        period_label="week",
        status="completed",
        file_path="x.json",
        file_size=10,
        row_count=1,
    )
    db.add(run)
    db.flush()
    mock_download.return_value = {
        "id": run.id,
        "name": "T",
        "format": "json",
        "download_url": f"/api/reports/runs/{run.id}/download",
    }
    mock_preview.return_value = ReportPreviewResponse(columns=["a"], rows=[["1"]], total_rows=1)
    out = preview_report(db, run.id)
    assert out["total_rows"] == 1


def test_resolve_target_run_prefers_xlsx(tmp_path, db, monkeypatch):
    monkeypatch.setattr("app.services.reports_service.REPORTS_DIR", tmp_path)
    json_path = tmp_path / "report_1_exception.json"
    json_path.write_text("[]", encoding="utf-8")
    xlsx_path = tmp_path / "report_2_tracking.xlsx"
    wb = __import__("openpyxl").Workbook()
    wb.active.append(["a", "b"])
    wb.save(xlsx_path)
    wb.close()

    db.add(
        ReportRun(
            slug="exception",
            name="Exception",
            category="exceptions",
            format="json",
            period_label="w",
            status="completed",
            file_path=str(json_path),
            row_count=0,
        )
    )
    db.add(
        ReportRun(
            slug="tracking",
            name="Tracking",
            category="shipments",
            format="xlsx",
            period_label="w",
            status="completed",
            file_path=str(xlsx_path),
            row_count=1,
        )
    )
    db.commit()

    snapshot = get_reports_center_snapshot(db, limit=5)
    plan = ReportsPlan(
        task_type=ReportsTaskType.report_redownload,
        format_filter="xlsx",
        profile=ReportsProfile.DOWNLOAD,
    )
    chosen = resolve_target_run(db, plan, snapshot, require_file=True)
    assert chosen["format"] == "xlsx"


def test_resolve_run_path_stale_absolute(tmp_path, db, monkeypatch):
    monkeypatch.setattr("app.services.reports_service.REPORTS_DIR", tmp_path)
    from app.services.reports_service import get_run_file, resolve_run_path

    run = ReportRun(
        slug="stale-test",
        name="Stale",
        category="custom",
        format="json",
        period_label="w",
        status="completed",
        file_path=r"C:\old\clone\backend\data\reports\report_stale_test.json",
        row_count=1,
    )
    db.add(run)
    db.flush()
    canonical = tmp_path / f"report_{run.id}_stale-test.json"
    canonical.write_text('[{"id": 1}]', encoding="utf-8")
    db.commit()

    assert resolve_run_path(run) == canonical
    _, path = get_run_file(db, run.id)
    assert path == canonical
