"""Tests Phase 8 — rapport d'activité quotidien client."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.client_phase7.export_email_intent import (
    is_export_email_only_followup,
    wants_export_by_email,
)
from app.services.client_phase8.capabilities import CAP_DAILY_REPORT, has_daily_report_capability
from app.services.client_phase8.daily_report_charts import render_daily_report_charts
from app.services.client_phase8.daily_report_collector import DailyReportSnapshot, collect_daily_report
from app.services.client_phase8.daily_report_email import build_daily_report_html
from app.services.client_phase8.daily_report_intent import (
    fallback_plan_from_message,
    is_daily_report_workspace,
    parse_schedule_time_followup,
)
from app.services.client_phase8.daily_report_narrative import (
    factual_daily_report_narrative,
    generate_daily_report_narrative,
)
from app.services.client_phase8.daily_report_pdf import generate_daily_report_pdf
from app.services.client_phase8.daily_report_preferences import parse_run_time
from app.services.client_phase8.daily_report_scheduler import process_scheduled_daily_reports
from app.services.client_phase8.router import plan_daily_report_task, try_client_daily_report_turn
from app.schemas.user_notifications import UserNotificationRead


def _snapshot(**overrides) -> DailyReportSnapshot:
    now = datetime(2026, 6, 27, 18, 0, tzinfo=timezone.utc)
    base = DailyReportSnapshot(
        user_id=1,
        user_name="Test User",
        user_email="u@test.com",
        lang="fr",
        timezone="UTC",
        period_start_local=now,
        period_end_local=now,
        generated_at_local=now,
        kpi_messages=5,
        kpi_trackings=2,
        kpi_exports=1,
        kpi_watches=0,
        kpi_unread_notifications=3,
        kpi_sessions_today=2,
        hourly_activity={9: 2, 14: 5},
        shipment_status_counts={"in_transit": 1, "delivered": 1},
        notification_type_counts={"tracking_update": 2},
        shipments_today=[{"tracking_number": "881135077232", "status": "In transit", "location": "CDG", "time": "10:00"}],
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_is_daily_report_workspace():
    assert is_daily_report_workspace("Envoie mon rapport du jour par mail")
    assert is_daily_report_workspace("Bilan de mon activité aujourd'hui")
    assert not is_daily_report_workspace("Où est mon colis 881135077232 ?")
    assert not is_daily_report_workspace("Exporte le PDF du colis par mail")


def test_daily_report_excludes_phase7_export():
    assert not wants_export_by_email("Envoie mon rapport du jour par mail")
    assert not is_export_email_only_followup("Rapport quotidien par email")


def test_parse_run_time():
    assert parse_run_time("chaque jour à 18h") == "18:00"
    assert parse_run_time("18:30") == "18:30"
    assert parse_schedule_time_followup("18h") == "18:00"


def test_fallback_plan_send_and_schedule():
    send = fallback_plan_from_message("rapport du jour par mail", lang="fr")
    assert send and send["task_type"] == "send_daily_report"
    sched = fallback_plan_from_message("envoie chaque jour à 17h", lang="fr")
    assert sched and sched["task_type"] == "configure_schedule"
    assert sched["answers"]["run_time"] == "17:00"
    disable = fallback_plan_from_message("arrête le rapport quotidien", lang="fr")
    assert disable and disable["task_type"] == "disable_schedule"


@patch("app.services.client_phase8.capabilities.get_settings")
def test_has_daily_report_capability(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_capabilities=f"chat,{CAP_DAILY_REPORT}",
        client_agent_router_enabled=True,
    )
    assert has_daily_report_capability()


def test_narrative_factual_fallback():
    snap = _snapshot()
    text = factual_daily_report_narrative(snap)
    assert "5" in text or "message" in text.lower()


@patch("app.services.client_phase8.router._call_ollama_plan")
def test_plan_daily_report_fast_path_skips_ollama(mock_ollama):
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=9)
    db = MagicMock()
    plan = plan_daily_report_task(
        db,
        user,
        session,
        "envoie moi le rapport du jour par mail",
        exclude_message_id=1,
        ui_language="fr",
    )
    assert plan is not None
    assert plan["task_type"] == "send_daily_report"
    mock_ollama.assert_not_called()


@patch("app.services.client_phase8.daily_report_collector._utc_now")
@patch("app.services.client_phase8.daily_report_collector.get_daily_usage")
@patch("app.services.client_phase8.daily_report_collector.fetch_notifications_for_query")
@patch("app.services.client_phase8.daily_report_collector.list_user_sessions")
def test_collect_daily_report_utc(mock_sessions, mock_notifs, mock_usage, mock_now):
    fixed = datetime(2026, 6, 27, 15, 30, tzinfo=timezone.utc)
    mock_now.return_value = fixed
    mock_usage.return_value = {"messages_today": 1, "trackings_today": 0, "exports_today": 0}
    unread = SimpleNamespace(items=[], unread_count=0, total=0)
    today = SimpleNamespace(items=[], unread_count=0, total=0)
    mock_notifs.side_effect = [unread, today]
    mock_sessions.return_value = []
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    user = SimpleNamespace(id=1, full_name="Test", email="u@test.com", preferred_language="fr")
    snap = collect_daily_report(db, user, lang="fr")
    assert snap.timezone == "UTC"
    assert snap.period_start_local.hour == 0
    assert snap.period_end_local == fixed
    assert snap.kpi_messages == 1


@patch("app.services.client_phase8.router.router_enabled", return_value=True)
@patch("app.services.client_phase8.router.has_daily_report_capability", return_value=True)
@patch("app.services.client_phase8.router.execute_send_daily_report", side_effect=RuntimeError("boom"))
def test_send_daily_report_explicit_error(_exec, _cap, _router):
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=9)
    db = MagicMock()
    turn = try_client_daily_report_turn(
        db, user, session, "rapport du jour par mail", 1, "fr"
    )
    assert turn is not None
    assert turn["intent"] == "send_daily_report_failed"
    assert "Impossible" in turn["reply"]


def test_charts_render_png():
    charts = render_daily_report_charts(_snapshot())
    assert "hourly" in charts
    assert charts["hourly"][:8] == b"\x89PNG\r\n\x1a\n"


def test_pdf_generation():
    snap = _snapshot()
    narrative = "Synthèse test du jour."
    pdf_bytes, filename = generate_daily_report_pdf(snap, narrative=narrative, chart_pngs={})
    assert pdf_bytes[:4] == b"%PDF"
    assert filename.startswith("rapport-activite")


def test_html_email_body():
    html = build_daily_report_html(_snapshot(), narrative="Test narrative")
    assert "Indicateurs clés" in html
    assert "Test narrative" in html


@patch("app.services.client_phase8.daily_report_executor.is_email_configured", return_value=True)
@patch("app.services.client_phase8.daily_report_executor.send_daily_report_email", return_value=True)
@patch("app.services.client_phase8.daily_report_executor.build_daily_report_bundle")
def test_execute_send_daily_report(mock_bundle, mock_send, _smtp):
    from app.services.client_phase8.daily_report_executor import execute_send_daily_report

    snap = _snapshot()
    mock_bundle.return_value = (snap, "Narrative", b"%PDF", "rapport.pdf")
    user = SimpleNamespace(id=1, email="u@test.com", full_name="Test", preferred_language="fr")
    db = MagicMock()
    ok, msg, result = execute_send_daily_report(db, user, lang="fr")
    assert ok is True
    assert "u@test.com" in msg
    assert result is not None
    mock_send.assert_called_once()


@patch("app.services.client_phase8.router.router_enabled", return_value=True)
@patch("app.services.client_phase8.router.has_daily_report_capability", return_value=True)
@patch("app.services.client_phase8.router.execute_send_daily_report")
@patch("app.services.client_phase8.router.plan_daily_report_task")
def test_try_client_daily_report_turn_send(mock_plan, mock_exec, _cap, _router):
    mock_plan.return_value = {
        "task_type": "send_daily_report",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    mock_exec.return_value = (True, "Envoyé à u@test.com", _snapshot())
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=9)
    db = MagicMock()
    turn = try_client_daily_report_turn(db, user, session, "rapport du jour par mail", 1, "fr")
    assert turn is not None
    assert turn["intent"] == "send_daily_report"
    assert turn["source"] == "agent_daily_report"


@patch("app.services.client_phase8.router.router_enabled", return_value=True)
@patch("app.services.client_phase8.router.has_daily_report_capability", return_value=True)
@patch("app.services.client_phase8.router.plan_daily_report_task")
def test_schedule_unavailable_message(mock_plan, _cap, _router):
    mock_plan.return_value = {
        "task_type": "configure_schedule",
        "assistant_intro": "",
        "answers": {"run_time": "18:00"},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=9)
    db = MagicMock()
    turn = try_client_daily_report_turn(db, user, session, "envoie chaque jour à 18h", 1, "fr")
    assert turn is not None
    assert turn["intent"] == "schedule_unavailable"
    assert "pas disponible" in turn["reply"].lower()


@patch("app.services.client_phase8.daily_report_executor.is_email_configured", return_value=True)
@patch("app.services.client_phase8.daily_report_executor.send_daily_report_email", return_value=True)
@patch(
    "app.services.client_phase8.daily_report_executor.render_daily_report_charts",
    side_effect=ModuleNotFoundError("matplotlib"),
)
@patch("app.services.client_phase8.daily_report_executor.collect_daily_report")
def test_build_bundle_without_matplotlib(mock_collect, _charts, mock_send, _smtp):
    from app.services.client_phase8.daily_report_executor import execute_send_daily_report

    snap = _snapshot()
    mock_collect.return_value = snap
    user = SimpleNamespace(id=1, email="u@test.com", full_name="Test", preferred_language="fr")
    db = MagicMock()
    ok, msg, result = execute_send_daily_report(db, user, lang="fr")
    assert ok is True
    assert result is not None
    mock_send.assert_called_once()


@patch("app.services.client_phase8.daily_report_scheduler.execute_send_daily_report")
def test_scheduler_dedup_and_time_match(mock_send):
    mock_send.return_value = (True, "ok", _snapshot())
    settings_row = SimpleNamespace(
        user_id=1,
        enabled=True,
        run_time="18:00",
        timezone="UTC",
        last_sent_local_date=None,
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [settings_row]
    db.get.return_value = user

    fixed = datetime(2026, 6, 27, 18, 0, tzinfo=timezone.utc)

    with patch("app.services.client_phase8.daily_report_scheduler.local_now", return_value=fixed):
        with patch("app.services.client_phase8.daily_report_scheduler.mark_sent_today") as mock_mark:
            count = process_scheduled_daily_reports(db)
    assert count == 1
    mock_send.assert_called_once()
    mock_send.assert_called_with(
        db,
        user,
        lang="fr",
        use_llm_narrative=True,
    )
    mock_mark.assert_called_once()


@patch("app.services.client_phase8.daily_report_collector.get_daily_usage")
@patch("app.services.client_phase8.daily_report_collector.fetch_notifications_for_query")
@patch("app.services.client_phase8.daily_report_collector.list_user_sessions")
def test_collect_daily_report(mock_sessions, mock_notifs, mock_usage):
    mock_usage.return_value = {"messages_today": 3, "trackings_today": 1, "exports_today": 0}
    unread = SimpleNamespace(items=[], unread_count=2, total=2)
    today = SimpleNamespace(items=[], unread_count=0, total=0)
    mock_notifs.side_effect = [unread, today]
    mock_sessions.return_value = []
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    user = SimpleNamespace(id=1, full_name="Test", email="u@test.com", preferred_language="fr")
    snap = collect_daily_report(db, user, lang="fr")
    assert snap.kpi_messages == 3
    assert snap.kpi_unread_notifications == 2
    assert snap.timezone == "UTC"


def test_important_notification_detection():
    item = UserNotificationRead(
        id=1,
        user_id=1,
        type="security_alert",
        title="Alerte",
        message="Test",
        status="unread",
        priority="high",
        created_at=datetime.now(timezone.utc),
    )
    snap = _snapshot(important_notifications=[item], unread_notifications=[item])
    assert len(snap.important_notifications) == 1
