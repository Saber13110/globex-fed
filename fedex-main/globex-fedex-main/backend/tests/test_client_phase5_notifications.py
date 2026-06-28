"""Tests Phase 5 — routeur notifications (mocks Ollama)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.client_notification import ClientNotification
from app.services.client_phase5.notification_executor import execute_notifications_query
from app.services.client_phase5.notification_filters import (
    NotificationQueryParams,
    apply_read_intent_to_plan,
    build_read_clarification_plan,
    detect_read_intent,
    extract_notification_limit,
    fallback_plan_from_message,
    is_notification_workspace,
    is_read_clarification_followup,
    params_from_answers,
    parse_read_clarification_reply,
    read_clarification_message,
    reconcile_notification_plan,
    sanitize_phantom_filters,
    section_to_api_type,
)
from app.services.client_phase5.notification_executor import execute_mark_all_read
from app.services.client_phase5.router import (
    _read_clarification_followup_plan,
    plan_notifications_task,
    try_client_notifications_turn,
)


def test_notification_workspace_variants():
    assert is_notification_workspace("Montre toutes mes notifications")
    assert is_notification_workspace("Y a-t-il des alertes ?")
    assert is_notification_workspace("Qu'est-ce que je n'ai pas lu ?")


def test_tracking_live_not_notification_workspace():
    assert not is_notification_workspace("Où est mon colis 881135077232 ?")


def test_session_message_not_notification_workspace():
    assert not is_notification_workspace("Donne mes conversations récentes")


def test_section_to_api_type_tracking():
    assert section_to_api_type("tracking") == "tracking_update"
    assert section_to_api_type("support") == "support"


def test_reconcile_sets_summarize_and_tracking():
    plan = reconcile_notification_plan(
        "Résume mes alertes suivi colis",
        {
            "task_type": "notifications_query",
            "answers": {"mode": "list", "section": "all"},
        },
    )
    answers = plan["answers"]
    assert answers["mode"] == "summarize"
    assert answers["section"] == "tracking"


def test_reconcile_pdf_mode():
    plan = reconcile_notification_plan(
        "Télécharge mes notifications en pdf",
        {"task_type": "notifications_query", "answers": {"mode": "list"}},
    )
    assert plan["answers"]["mode"] == "export_pdf"
    assert plan["answers"]["attach_pdf"] is True


def test_fallback_plan_offline():
    plan = fallback_plan_from_message("Montre mes notifications")
    assert plan is not None
    assert plan["task_type"] == "notifications_query"
    assert plan["answers"]["mode"] == "list"


def test_params_from_answers_export_pdf():
    params = params_from_answers({"mode": "export_pdf", "section": "support", "limit": 20})
    assert params.mode == "export_pdf"
    assert params.attach_pdf is True
    assert params.section == "support"


@patch("app.services.client_phase5.notification_executor.has_capability", return_value=True)
@patch("app.services.client_phase5.notification_executor.fetch_notifications_for_query")
def test_list_mode_chat_no_export(mock_fetch, _mock_cap):
    mock_fetch.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                title="Alerte",
                message="Test",
                is_read=False,
                created_at=datetime.now(timezone.utc),
                related_tracking_number="",
                type="system_alert",
            )
        ],
        unread_count=1,
        total=1,
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=5)
    params = NotificationQueryParams(mode="list", section="all")
    reply, export = execute_notifications_query(db, user, session, params, ui_language="fr")
    assert "notification" in reply.lower()
    assert export is None


@patch("app.services.client_phase5.notification_executor.has_capability", return_value=True)
@patch("app.services.client_phase5.notification_executor.build_notifications_pdf_artifact")
@patch("app.services.client_phase5.notification_executor.fetch_notifications_for_query")
def test_export_pdf_mode(mock_fetch, mock_pdf, _mock_cap):
    mock_fetch.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                title="Support",
                message="Réponse admin",
                is_read=True,
                created_at=datetime.now(timezone.utc),
                related_tracking_number="",
                type="admin_reply",
            )
        ],
        unread_count=0,
        total=1,
    )
    mock_pdf.return_value = (
        {"format": "pdf", "filename": "notifications.pdf", "export_token": "abc"},
        b"%PDF",
        "notifications.pdf",
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=5)
    params = NotificationQueryParams(mode="export_pdf", section="support", attach_pdf=True)
    reply, export = execute_notifications_query(db, user, session, params, ui_language="fr")
    assert export is not None
    assert export["format"] == "pdf"
    mock_pdf.assert_called_once()


@patch("app.services.client_phase5.notification_executor.has_capability", return_value=False)
@patch("app.services.client_phase5.notification_executor.fetch_notifications_for_query")
def test_pdf_requires_pdf_capability(mock_fetch, _mock_cap):
    mock_fetch.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                title="A",
                message="B",
                is_read=False,
                created_at=datetime.now(timezone.utc),
                related_tracking_number="",
                type="tracking_update",
            )
        ],
        unread_count=1,
        total=1,
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=5)
    params = NotificationQueryParams(mode="export_pdf", attach_pdf=True)
    reply, export = execute_notifications_query(db, user, session, params, ui_language="fr")
    assert export is None
    assert "pdf" in reply.lower()


@patch("app.services.client_phase5.router.router_enabled", return_value=False)
def test_try_returns_none_flag_off(_mock_flag):
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=1)
    assert try_client_notifications_turn(db, user, session, "mes notifications", None, "fr") is None


@patch("app.services.client_phase5.notification_executor.fetch_notifications_for_query")
def test_empty_filter_result(mock_fetch):
    mock_fetch.return_value = SimpleNamespace(items=[], unread_count=0, total=0)
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=5)
    params = NotificationQueryParams(mode="list", section="tracking")
    reply, export = execute_notifications_query(db, user, session, params, ui_language="fr")
    assert "Aucune notification" in reply
    assert export is None


@patch("app.services.client_phase5.router._call_ollama_notifications_plan")
@patch("app.services.client_phase5.router.build_conversation_history_for_llm", return_value="")
def test_plan_notifications_task_mock(mock_hist, mock_ollama):
    mock_ollama.return_value = {
        "task_type": "notifications_query",
        "answers": {"mode": "list", "section": "unread", "status": "unread"},
        "ready_to_execute": True,
    }
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=1)
    plan = plan_notifications_task(
        db, user, session, "mes notifications non lues", exclude_message_id=None, ui_language="fr"
    )
    assert plan is not None
    assert plan["task_type"] == "notifications_query"
    assert plan["answers"]["status"] == "unread"


@patch("app.services.client_phase5.notification_summary_llm.call_ollama_session_summary")
@patch("app.services.client_phase5.notification_summary_llm.is_acceptable_summary", return_value=False)
def test_summarize_mode_factual_fallback(mock_accept, mock_ollama):
    from app.schemas.user_notifications import UserNotificationRead

    mock_ollama.return_value = "pitch marketing FedEx"
    item = UserNotificationRead(
        id=1,
        user_id=1,
        type="tracking_update",
        title="Mise à jour",
        message="En transit",
        status="unread",
        is_read=False,
        created_at=datetime.now(timezone.utc),
        related_tracking_number="881135077232",
    )
    from app.services.client_phase5.notification_summary_llm import generate_notifications_summary

    result = generate_notifications_summary([item], lang="fr", filter_label="suivi colis")
    assert "881135077232" in result or "notification" in result.lower()


def test_extract_limit_dernier_5():
    assert extract_notification_limit("liste moi mes dernier 5 notifcations") == 5


def test_extract_limit_juste_les_3():
    assert extract_notification_limit("juste les 3 alertes") == 3


def test_reconcile_forces_limit_from_message():
    plan = reconcile_notification_plan(
        "liste mes 5 dernières notifications",
        {
            "task_type": "notifications_query",
            "answers": {"mode": "list", "section": "all", "limit": 30},
        },
    )
    assert plan["answers"]["limit"] == 5


def test_default_limit_list_is_15():
    params = params_from_answers({"mode": "list", "section": "all"})
    assert params.limit == 15


def test_default_limit_summarize_is_30():
    params = params_from_answers({"mode": "summarize", "section": "all"})
    assert params.limit == 30


@patch("app.services.client_phase5.notification_executor.has_capability", return_value=True)
@patch("app.services.client_phase5.notification_executor.fetch_notifications_for_query")
def test_list_displays_exactly_5_items(mock_fetch, _mock_cap):
    items = [
        SimpleNamespace(
            title=f"Alerte {i}",
            message="Test",
            is_read=False,
            created_at=datetime.now(timezone.utc),
            related_tracking_number="",
            type="system_alert",
        )
        for i in range(10)
    ]
    mock_fetch.return_value = SimpleNamespace(items=items[:5], unread_count=10, total=100)
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=5)
    params = NotificationQueryParams(mode="list", section="all", limit=5)
    reply, export = execute_notifications_query(db, user, session, params, ui_language="fr")
    assert export is None
    assert reply.count("\n   ") == 5
    assert "6. " not in reply
    assert "Affichage des 5 plus récentes" in reply


@patch("app.services.client_phase5.notification_executor.has_capability", return_value=True)
@patch("app.services.client_phase5.notification_executor.fetch_notifications_for_query")
def test_assistant_intro_preserved(mock_fetch, _mock_cap):
    mock_fetch.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                title="Alerte",
                message="Test",
                is_read=False,
                created_at=datetime.now(timezone.utc),
                related_tracking_number="",
                type="system_alert",
            )
        ],
        unread_count=1,
        total=1,
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=5)
    params = NotificationQueryParams(mode="list", section="all", limit=5)
    reply, _export = execute_notifications_query(
        db,
        user,
        session,
        params,
        ui_language="fr",
        assistant_intro="Voici vos 5 notifications les plus récentes.",
    )
    assert reply.startswith("Voici vos 5 notifications les plus récentes.")


@patch("app.services.client_phase5.router._call_ollama_notifications_plan")
@patch("app.services.client_phase5.router.build_conversation_history_for_llm", return_value="")
def test_router_retry_on_conversation_misroute(mock_hist, mock_ollama):
    mock_ollama.side_effect = [
        {"task_type": "conversation", "answers": {}, "ready_to_execute": True},
        {
            "task_type": "notifications_query",
            "answers": {"mode": "list", "section": "all", "limit": 5},
            "ready_to_execute": True,
        },
    ]
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=1)
    plan = plan_notifications_task(
        db,
        user,
        session,
        "liste moi mes dernier 5 notifcations",
        exclude_message_id=None,
        ui_language="fr",
    )
    assert plan is not None
    assert plan["task_type"] == "notifications_query"
    assert plan["answers"]["limit"] == 5
    assert mock_ollama.call_count == 2


def test_detect_read_intent_ambiguous_rend():
    assert detect_read_intent("je veux que tu me rend les notifications comme deja lu") == "ambiguous"


def test_detect_read_intent_list_read():
    assert detect_read_intent("montre mes notifications déjà lues") == "list_read"


def test_detect_read_intent_mark_all():
    assert detect_read_intent("marque toutes mes notifs comme lues") == "mark_all"


def test_sanitize_phantom_support_and_limit_1():
    answers = sanitize_phantom_filters(
        "liste mes notifications",
        {"section": "support", "limit": 1, "mode": "list"},
    )
    assert answers["section"] == "all"
    assert answers["limit"] == 15


def test_reconcile_status_read():
    plan = reconcile_notification_plan(
        "montre mes notifications déjà lues",
        {"task_type": "notifications_query", "answers": {"mode": "list", "section": "all"}},
    )
    assert plan["answers"]["status"] == "read"
    assert plan["answers"]["section"] == "all"


def test_ambiguous_returns_clarification_not_list():
    plan = fallback_plan_from_message("je veux que tu me rend les notifications comme deja lu")
    assert plan is not None
    assert plan["needs_clarification"] is True
    assert "voir" in plan["clarification_question"].lower()
    assert plan.get("ready_to_execute") is False


def test_apply_read_intent_ambiguous_overrides_ollama_hallucination():
    plan = apply_read_intent_to_plan(
        "je veux que tu me rend les notifications comme deja lu",
        {
            "task_type": "notifications_query",
            "answers": {"mode": "list", "section": "support", "limit": 1, "status": "read"},
            "ready_to_execute": True,
        },
        lang="fr",
    )
    assert plan["needs_clarification"] is True


@patch("app.services.client_phase5.notification_executor.mark_all_user_notifications_read", return_value=42)
def test_execute_mark_all_read(mock_mark):
    db = MagicMock()
    reply = execute_mark_all_read(db, 1, lang="fr")
    assert "42" in reply
    mock_mark.assert_called_once_with(db, 1)


def test_read_clarification_followup_marquer():
    db = MagicMock()
    clarification = read_clarification_message("fr")
    with patch(
        "app.services.client_phase5.router._last_bot_message_text",
        return_value=clarification,
    ):
        plan = _read_clarification_followup_plan(db, 1, "marquer", lang="fr")
    assert plan is not None
    assert plan["task_type"] == "notifications_mark_all_read"


def test_read_clarification_followup_voir():
    db = MagicMock()
    clarification = read_clarification_message("fr")
    with patch(
        "app.services.client_phase5.router._last_bot_message_text",
        return_value=clarification,
    ):
        plan = _read_clarification_followup_plan(db, 1, "voir", lang="fr")
    assert plan is not None
    assert plan["answers"]["status"] == "read"


def test_is_read_clarification_followup():
    assert is_read_clarification_followup(read_clarification_message("fr"))
    assert not is_read_clarification_followup("Voici vos 5 notifications")


def test_parse_read_clarification_reply():
    assert parse_read_clarification_reply("marquer") == "mark_all"
    assert parse_read_clarification_reply("voir") == "list_read"
    assert parse_read_clarification_reply("bonjour") is None


def test_filter_by_tracking_number_sqlite():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base
    from app.models.user import User
    from app.services.user_notification_service import list_user_notifications

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    user = User(
        email="u@test.com",
        password_hash="x",
        full_name="U",
        role="client",
        status="active",
        organization_id="org-test-1",
    )
    db.add(user)
    db.flush()
    db.add(
        ClientNotification(
            user_id=user.id,
            kind="tracking_update",
            title="Colis A",
            message="Transit",
            related_tracking_number="881135077232",
        )
    )
    db.add(
        ClientNotification(
            user_id=user.id,
            kind="tracking_update",
            title="Colis B",
            message="Livré",
            related_tracking_number="999999999999",
        )
    )
    db.commit()
    result = list_user_notifications(db, user.id, type="tracking_update", tracking_number="881135077232")
    assert len(result.items) == 1
    assert result.items[0].related_tracking_number == "881135077232"
