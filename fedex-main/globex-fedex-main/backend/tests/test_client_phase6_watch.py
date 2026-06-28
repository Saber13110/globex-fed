"""Tests Phase 6 — surveillance colis + alertes mail (mocks Ollama / FedEx / SMTP)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.shipment_watch import ShipmentWatch
from app.services.client_phase6 import capabilities
from app.services.client_phase6.router import (
    _parse_json_object,
    _plan_from_data,
    plan_watch_task,
    try_client_watch_turn,
)
from app.services.client_phase6.watch_intent import (
    extract_email_update_limit,
    fallback_plan_from_message,
    is_watch_workspace,
    parse_email_limit_reply,
    reconcile_watch_plan,
)
from app.services.shipment_watch_service import (
    _try_send_watch_update_email,
    _watch_email_limit_reached,
    notify_watch_visibility_event,
)


def test_parse_json_object_from_fence():
    raw = '```json\n{"task_type": "activate_watch"}\n```'
    data = _parse_json_object(raw)
    assert data is not None
    assert data["task_type"] == "activate_watch"


def test_plan_from_data_normalizes_task():
    plan = _plan_from_data(
        {
            "task_type": "activate_watch",
            "answers": {"tracking_number": "881135077232", "max_email_updates": 3},
            "ready_to_execute": True,
        }
    )
    assert plan["task_type"] == "activate_watch"
    assert plan["answers"]["max_email_updates"] == 3


def test_plan_from_data_invalid_task_becomes_conversation():
    plan = _plan_from_data({"task_type": "hack_everything"})
    assert plan["task_type"] == "conversation"


def test_is_watch_workspace_activate():
    assert is_watch_workspace("Préviens-moi par mail pour le colis 881135077232")
    assert is_watch_workspace("Surveille mon colis et envoie un email")


def test_live_tracking_not_watch_workspace():
    assert not is_watch_workspace("Où est mon colis 881135077232 ?")


def test_notifications_inbox_not_watch_workspace():
    assert not is_watch_workspace("Montre toutes mes notifications")


def test_extract_email_update_limit():
    assert extract_email_update_limit("préviens par mail 3 fois") == 3
    assert extract_email_update_limit("surveille illimité") is None
    assert extract_email_update_limit("surveille par mail") == "missing"


def test_parse_email_limit_reply():
    assert parse_email_limit_reply("5") == 5
    assert parse_email_limit_reply("illimité") is None
    assert parse_email_limit_reply("peut-être") == "invalid"


def test_fallback_plan_with_limit():
    plan = fallback_plan_from_message(
        "Préviens-moi par mail pour 881135077232, 3 fois",
        lang="fr",
    )
    assert plan is not None
    assert plan["task_type"] == "activate_watch"
    assert plan["answers"]["tracking_number"] == "881135077232"
    assert plan["answers"]["max_email_updates"] == 3
    assert plan["ready_to_execute"] is True


def test_fallback_plan_needs_email_limit():
    plan = fallback_plan_from_message("Surveille le colis 881135077232 par mail", lang="fr")
    assert plan is not None
    assert plan["needs_clarification"] is True
    assert "Combien de mails" in plan["clarification_question"]


def test_reconcile_requires_limit_when_missing():
    plan = reconcile_watch_plan(
        "Surveille 881135077232 par email",
        {
            "task_type": "activate_watch",
            "answers": {"tracking_number": "881135077232", "notify_email": True},
            "needs_clarification": False,
        },
        lang="fr",
    )
    assert plan["needs_clarification"] is True


@patch.object(capabilities, "get_settings")
def test_try_client_watch_turn_none_when_router_disabled(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=False,
        client_agent_capabilities="chat,fedex,watch",
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr", email="u@test.com")
    session = SimpleNamespace(id=1)
    assert try_client_watch_turn(db, user, session, "surveille par mail", 1, "fr") is None


@patch.object(capabilities, "get_settings")
def test_try_client_watch_turn_none_without_watch_cap(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="chat,fedex,sessions,notifications",
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr", email="u@test.com")
    session = SimpleNamespace(id=1)
    assert try_client_watch_turn(db, user, session, "surveille par mail", 1, "fr") is None


@patch.object(capabilities, "get_settings")
@patch("app.services.client_phase6.router.plan_watch_task")
def test_try_client_watch_turn_activate(mock_plan, mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="chat,fedex,watch",
    )
    mock_plan.return_value = {
        "task_type": "activate_watch",
        "assistant_intro": "C'est noté.",
        "answers": {
            "tracking_number": "881135077232",
            "notify_email": True,
            "notify_in_app": True,
            "max_email_updates": 3,
            "alert_type": "all",
        },
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr", email="u@test.com", full_name="Test")
    session = SimpleNamespace(id=1)

    with patch(
        "app.services.client_phase6.watch_executor.activate_client_shipment_watch"
    ) as mock_activate:
        watch = SimpleNamespace(
            tracking_number="881135077232",
            max_email_updates=3,
            notify_email=True,
        )
        mock_activate.return_value = {
            "watch": watch,
            "confirmation_sent": True,
            "status": "In transit",
            "location": "Paris",
        }
        result = try_client_watch_turn(
            db,
            user,
            session,
            "Préviens-moi par mail pour 881135077232, 3 fois",
            1,
            "fr",
        )

    assert result is not None
    assert result["intent"] == "activate_watch"
    assert "Surveillance active" in result["reply"]
    mock_activate.assert_called_once()
    call_kw = mock_activate.call_args.kwargs
    assert call_kw["max_email_updates"] == 3


@patch.object(capabilities, "get_settings")
@patch("app.services.client_phase6.router.plan_watch_task")
def test_try_client_watch_turn_stop(mock_plan, mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="watch",
    )
    mock_plan.return_value = {
        "task_type": "stop_watch",
        "assistant_intro": "",
        "answers": {"tracking_number": "881135077232"},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr", email="u@test.com")
    session = SimpleNamespace(id=1)

    with patch("app.services.client_phase6.watch_executor.deactivate_user_watches") as mock_stop:
        mock_stop.return_value = [SimpleNamespace(tracking_number="881135077232")]
        result = try_client_watch_turn(db, user, session, "Arrête les alertes colis", 1, "fr")

    assert result is not None
    assert result["intent"] == "stop_watch"
    mock_stop.assert_called_once()


def test_watch_email_limit_reached():
    watch = ShipmentWatch(
        user_id=1,
        tracking_number="881135077232",
        max_email_updates=2,
        email_updates_sent=2,
    )
    assert _watch_email_limit_reached(watch) is True


@patch("app.services.shipment_watch_service.send_email")
@patch("app.services.shipment_watch_service.is_email_configured", return_value=True)
def test_try_send_watch_respects_limit(mock_smtp_cfg, mock_send):
    watch = ShipmentWatch(
        user_id=1,
        tracking_number="881135077232",
        notify_email=True,
        max_email_updates=2,
        email_updates_sent=2,
    )
    user = SimpleNamespace(id=1, email="u@test.com", full_name="Test")
    sent = _try_send_watch_update_email(
        user,
        watch,
        subject="Test",
        body="Body",
    )
    assert sent is False
    mock_send.assert_not_called()


@patch("app.services.shipment_watch_service.send_email", return_value=True)
@patch("app.services.shipment_watch_service.is_email_configured", return_value=True)
def test_try_send_watch_increments_counter(mock_smtp_cfg, mock_send):
    watch = ShipmentWatch(
        user_id=1,
        tracking_number="881135077232",
        notify_email=True,
        max_email_updates=3,
        email_updates_sent=1,
    )
    user = SimpleNamespace(id=1, email="u@test.com", full_name="Test")
    sent = _try_send_watch_update_email(user, watch, subject="S", body="B")
    assert sent is True
    assert watch.email_updates_sent == 2


@patch("app.services.shipment_watch_service.send_email")
@patch("app.services.shipment_watch_service.is_email_configured", return_value=True)
@patch("app.services.shipment_watch_service.create_user_notification")
def test_notify_visibility_skips_email_when_limit(mock_notif, mock_smtp_cfg, mock_send):
    watch = ShipmentWatch(
        user_id=1,
        tracking_number="881135077232",
        notify_email=True,
        notify_in_app=True,
        max_email_updates=1,
        email_updates_sent=1,
        alert_type="all",
    )
    user = SimpleNamespace(id=1, email="u@test.com", full_name="Test")
    event = SimpleNamespace(
        event_type="IN_TRANSIT",
        description="Arrived at hub",
        location="Paris",
    )
    db = MagicMock()
    notify_watch_visibility_event(db, user=user, watch=watch, event=event)
    mock_send.assert_not_called()


@patch("app.services.client_phase6.router._call_ollama_watch_plan")
@patch.object(capabilities, "get_settings")
def test_plan_watch_task_ollama(mock_settings, mock_ollama):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="watch",
    )
    mock_ollama.return_value = {
        "task_type": "activate_watch",
        "answers": {
            "tracking_number": "881135077232",
            "max_email_updates": 5,
            "notify_email": True,
        },
        "needs_clarification": False,
    }
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=1)
    plan = plan_watch_task(
        db,
        user,
        session,
        "Préviens par mail 881135077232 max 5 mails",
        exclude_message_id=1,
        ui_language="fr",
    )
    assert plan is not None
    assert plan["task_type"] == "activate_watch"
    assert plan["answers"]["max_email_updates"] == 5
