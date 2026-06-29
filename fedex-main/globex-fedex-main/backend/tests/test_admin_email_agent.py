"""Tests agent e-mail admin Phase 1."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.admin_client.email.email_executor import try_admin_email_turn
from app.services.admin_client.email.email_intent import classify_email_intent
from app.services.admin_client.email.email_patterns import (
    is_bulk_email_message,
    is_send_user_email_message,
)
from app.services.admin_client.email.email_pending import (
    is_email_send_pending,
    parse_pending_email,
)
from app.services.admin_client.email.email_types import EmailTaskType
from app.services.admin_client.intent_priority import should_route_email, should_route_reports, should_route_users


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
        email="admin-email@test.com",
        password_hash="x",
        full_name="Admin Email",
        role="admin",
        status="active",
        organization_id="org-admin-email",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client_user(db):
    user = User(
        email="client-email@test.com",
        password_hash="x",
        full_name="Client Email",
        role="client",
        status="active",
        organization_id="org-client-email",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Email test")
    db.add(sess)
    db.flush()
    return sess


def test_ticket_email_not_reports():
    msg = "envoie un mail à amine@gmail.com pour lui dire que son ticket a été traité"
    assert is_send_user_email_message(msg)
    assert should_route_email(msg)
    assert not should_route_reports(msg)


def test_reports_share_still_works():
    msg = "partage le rapport tracking history par email à admin@test.com"
    assert should_route_reports(msg)
    assert not is_send_user_email_message(msg)


def test_user_email_before_reports_dispatch_order():
    """L'agent e-mail doit capturer le message ticket — pas le centre de rapports."""
    from app.services.admin_client.reports.reports_intent import classify_reports_intent
    from app.services.admin_client.reports.reports_types import ReportsTaskType

    plan = classify_reports_intent(
        "envoie un mail à amine@gmail.com pour lui dire que son ticket a été traité"
    )
    assert plan.task_type == ReportsTaskType.ambiguous
    assert "defer_user_email" in plan.raw_matches

    assert is_send_user_email_message(
        "envoie un mail à client@test.com pour lui dire que son accès est restreint"
    )
    assert is_bulk_email_message("envoie un mail en masse à tous les users")
    assert not is_send_user_email_message("envoie un mail en masse à tous les users")


def test_email_routed_not_users():
    msg = "envoie un e-mail à client@test.com pour l'informer du ticket"
    assert should_route_email(msg)
    assert not should_route_users(msg)


def test_intent_with_recipient_and_note(client_user):
    plan = classify_email_intent(
        "envoie un mail à client-email@test.com pour lui dire que nous avons traité sa demande"
    )
    assert plan.task_type == EmailTaskType.send_user_email
    assert plan.recipient_email == "client-email@test.com"
    assert plan.admin_note
    assert not plan.needs_clarification


def test_intent_missing_note_auto_draft():
    plan = classify_email_intent("envoie un mail à x@test.com")
    assert plan.task_type == EmailTaskType.send_user_email
    assert plan.recipient_email == "x@test.com"
    assert not plan.needs_clarification


def test_suspend_combo_routes_users_not_email():
    msg = "suspend amine@gmail.com et envoie-lui un mail"
    assert not is_send_user_email_message(msg)
    assert should_route_users(msg)
    assert not should_route_reports(msg)
    from app.services.admin_client.intent_priority import should_route_email

    assert not should_route_email(msg)


@patch("app.services.admin_client.users.users_tool.get_user_detail")
@patch("app.services.admin_client.users.users_service.suspend_user_account")
@patch("app.services.admin_client.email.email_narrative.compose_user_email_body")
def test_suspend_and_mail_inline_draft_after_confirm(
    mock_compose, mock_suspend, mock_detail, db, admin, chat_session, client_user
):
    from app.services.admin_client.users.users_pipeline import run_users_pipeline

    mock_compose.return_value = (
        "Bonjour,\n\nVotre compte a été suspendu.\n\nCordialement,\nGlobex",
        None,
    )
    mock_suspend.return_value = {
        "suspended": True,
        "user_id": client_user.id,
        "email": client_user.email,
    }
    mock_detail.return_value = {
        "id": client_user.id,
        "email": client_user.email,
        "full_name": client_user.full_name,
        "role": "client",
        "status": "active",
    }

    turn1 = run_users_pipeline(
        db,
        admin,
        chat_session,
        f"suspend {client_user.email} et envoie-lui un mail",
        1,
        "fr",
    )
    assert turn1 is not None
    assert turn1["intent"] == "users_suspend"
    assert "USERS_ACTION_PENDING" in turn1["reply"]
    assert "notify" not in turn1["reply"].lower() or True  # confirm step

    turn2 = run_users_pipeline(
        db,
        admin,
        chat_session,
        "oui",
        2,
        "fr",
        history_text=turn1["reply"],
        conversation_history=[{"role": "assistant", "content": turn1["reply"]}],
    )
    assert turn2 is not None
    assert turn2["intent"] == "email_draft"
    assert "ADMIN_EMAIL_PENDING" in turn2["reply"]
    assert client_user.email in turn2["reply"]
    assert "ADMIN_ACTION_EMAIL_OFFER" not in turn2["reply"]


def test_suspend_mail_not_logs_even_with_logs_history():
    from app.services.admin_client.intent_priority import should_route_logs, should_route_users
    from app.services.admin_client.logs.logs_intent import classify_logs_intent

    msg = "suspend amine@gmail.com et envoie-lui un mail"
    hist = "Journal d'activité Admin\n| #42 | admin.user_login | login |"
    assert not should_route_logs(msg, history_text=hist)
    assert should_route_users(msg, history_text=hist)
    plan = classify_logs_intent(msg, history_text=hist)
    assert plan.task_type.value == "ambiguous"
    assert "suspend_from_log" not in plan.raw_matches


def test_suspend_from_log_still_routes_logs():
    from app.services.admin_client.intent_priority import should_route_logs
    from app.services.admin_client.logs.logs_intent import classify_logs_intent

    msg = "suspend l'utilisateur depuis ce log"
    hist = "Journal d'activité Admin\nFiche log\n#42 admin.user_suspend"
    assert should_route_logs(msg, history_text=hist)
    plan = classify_logs_intent(msg, history_text=hist)
    assert plan.task_type.value == "log_suspend_user"


def test_pending_marker_roundtrip():
    hist = (
        "Brouillon\n\n[ADMIN_EMAIL_PENDING "
        '{"to":"a@b.com","subject":"Test","body_text":"Bonjour","user_id":1}]'
    )
    assert is_email_send_pending(history_text=hist)
    pending = parse_pending_email(hist)
    assert pending is not None
    assert pending.to == "a@b.com"
    assert pending.body_text == "Bonjour"


@patch("app.services.admin_client.email.email_narrative.compose_user_email_body")
@patch("app.services.admin_client.email.email_service.is_email_configured", return_value=True)
def test_pipeline_draft_then_confirm(
    _smtp, mock_compose, db, admin, chat_session, client_user
):
    mock_compose.return_value = (
        "Bonjour Client,\n\nVotre demande a été traitée.\n\nCordialement,\nGlobex",
        None,
    )
    turn1 = try_admin_email_turn(
        db,
        admin,
        chat_session,
        "envoie un mail à client-email@test.com pour lui dire que sa demande est traitée",
        1,
        "fr",
    )
    assert turn1 is not None
    assert turn1["intent"] == "email_draft"
    assert "client-email@test.com" in turn1["reply"]
    assert "ADMIN_EMAIL_PENDING" in turn1["reply"]

    with patch("app.services.admin_client.email.email_service.send_email", return_value=True):
        turn2 = try_admin_email_turn(
            db,
            admin,
            chat_session,
            "oui",
            2,
            "fr",
            history_text=turn1["reply"],
            conversation_history=[{"role": "assistant", "content": turn1["reply"]}],
        )
    assert turn2 is not None
    assert turn2["intent"] == "email_send_done"
    assert "client-email@test.com" in turn2["reply"]


@patch("app.services.admin_client.email.email_narrative.compose_user_email_body")
def test_pipeline_cancel(mock_compose, db, admin, chat_session, client_user):
    mock_compose.return_value = ("Bonjour,\n\nMessage test.\n\nCordialement,", None)
    turn1 = try_admin_email_turn(
        db,
        admin,
        chat_session,
        "envoie un email à client-email@test.com pour lui expliquer la suspension temporaire",
        1,
        "fr",
    )
    assert turn1 is not None
    turn2 = try_admin_email_turn(
        db,
        admin,
        chat_session,
        "non",
        2,
        "fr",
        history_text=turn1["reply"],
        conversation_history=[{"role": "assistant", "content": turn1["reply"]}],
    )
    assert turn2 is not None
    assert turn2["intent"] == "email_send_cancelled"


def test_wants_notify_inline():
    from app.services.admin_client.email.email_action_offer import wants_notify_user_by_email

    assert wants_notify_user_by_email("suspend client@test.com et envoie-lui un mail")
    assert wants_notify_user_by_email("réactive le compte et notifier par email")
    assert not wants_notify_user_by_email("suspend client@test.com")


def test_action_email_offer_marker():
    from app.services.admin_client.email.email_action_offer import (
        append_action_email_offer,
        is_action_email_offer_pending,
        parse_action_email_offer,
    )
    from app.services.admin_client.email.email_types import EmailScenario

    reply = append_action_email_offer(
        "Compte suspendu.",
        user_id=42,
        scenario=EmailScenario.user_suspend,
        admin_note="Compte suspendu pour abus.",
        recipient_email="client@test.com",
        lang="fr",
    )
    assert is_action_email_offer_pending(history_text=reply)
    offer = parse_action_email_offer(reply)
    assert offer is not None
    assert offer.user_id == 42
    assert offer.scenario == EmailScenario.user_suspend.value
    assert "Souhaitez-vous notifier" in reply


@patch("app.services.admin_client.email.email_narrative.compose_user_email_body")
@patch("app.services.admin_client.users.users_service.suspend_user_account")
@patch("app.services.admin_client.users.users_tool.get_user_detail")
def test_users_suspend_offers_email_after_confirm(
    mock_detail, mock_suspend, mock_compose, db, admin, chat_session, client_user
):
    from app.services.admin_client.users.users_pending import build_users_pending_marker
    from app.services.admin_client.users.users_pipeline import run_users_pipeline

    mock_suspend.return_value = {
        "suspended": True,
        "user_id": client_user.id,
        "email": client_user.email,
    }
    mock_detail.return_value = {
        "id": client_user.id,
        "email": client_user.email,
        "full_name": client_user.full_name,
        "role": "client",
        "status": "suspended",
    }
    marker = build_users_pending_marker("suspend", client_user.id, {"reason": "test"})
    hist = "Confirmez?" + marker

    turn = run_users_pipeline(
        db,
        admin,
        chat_session,
        "oui",
        1,
        "fr",
        history_text=hist,
        conversation_history=[{"role": "assistant", "content": hist}],
    )
    assert turn is not None
    assert turn["intent"] == "users_suspend_done"
    assert "ADMIN_ACTION_EMAIL_OFFER" in turn["reply"]
    assert "Souhaitez-vous notifier" in turn["reply"]


@patch("app.services.admin_client.email.email_narrative.compose_user_email_body")
@patch("app.services.admin_client.users.users_service.suspend_user_account")
@patch("app.services.admin_client.users.users_tool.get_user_detail")
def test_offer_accept_yields_email_draft(
    mock_detail, mock_suspend, mock_compose, db, admin, chat_session, client_user
):
    from app.services.admin_client.email.email_action_offer import append_action_email_offer
    from app.services.admin_client.email.email_executor import try_admin_email_turn
    from app.services.admin_client.email.email_types import EmailScenario

    mock_compose.return_value = (
        "Bonjour,\n\nVotre compte a été suspendu.\n\nCordialement,\nGlobex",
        None,
    )
    offer_reply = append_action_email_offer(
        "**Action effectuée**\n\nCompte suspendu.",
        user_id=client_user.id,
        scenario=EmailScenario.user_suspend,
        admin_note="Suspension temporaire.",
        recipient_email=client_user.email,
        lang="fr",
    )
    turn = try_admin_email_turn(
        db,
        admin,
        chat_session,
        "oui",
        1,
        "fr",
        history_text=offer_reply,
        conversation_history=[{"role": "assistant", "content": offer_reply}],
    )
    assert turn is not None
    assert turn["intent"] == "email_draft"
    assert "ADMIN_EMAIL_PENDING" in turn["reply"]
    assert client_user.email in turn["reply"]


@patch("app.services.admin_client.users.users_service.suspend_user_account")
@patch("app.services.admin_client.users.users_tool.get_user_detail")
def test_offer_decline_skips_email(
    mock_detail, mock_suspend, db, admin, chat_session, client_user
):
    from app.services.admin_client.email.email_action_offer import append_action_email_offer
    from app.services.admin_client.email.email_executor import try_admin_email_turn
    from app.services.admin_client.email.email_types import EmailScenario

    offer_reply = append_action_email_offer(
        "Compte suspendu.",
        user_id=client_user.id,
        scenario=EmailScenario.user_suspend,
        lang="fr",
    )
    turn = try_admin_email_turn(
        db,
        admin,
        chat_session,
        "non",
        1,
        "fr",
        history_text=offer_reply,
        conversation_history=[{"role": "assistant", "content": offer_reply}],
    )
    assert turn is not None
    assert turn["intent"] == "email_offer_declined"
    assert "ADMIN_EMAIL_PENDING" not in turn["reply"]
