"""Tests patterns et résolution générale tickets."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.services.admin_client.tickets.tickets_followup import resolve_ticket_id_from_context
from app.services.admin_client.tickets.tickets_intent import classify_tickets_intent
from app.services.admin_client.tickets.tickets_patterns import is_tickets_list_utterance
from app.services.admin_client.tickets.tickets_types import TicketsTaskType
from app.services.admin_client.tickets.tickets_workspace import is_tickets_workspace


def test_donne_moi_tous_les_tickets_engages_workspace():
    msg = "donne moi tous les tickets"
    assert is_tickets_list_utterance(msg)
    assert is_tickets_workspace(msg)
    plan = classify_tickets_intent(msg)
    assert plan.task_type == TicketsTaskType.ticket_list
    assert plan.status_filter == "all"


def test_liste_moi_variant():
    assert is_tickets_list_utterance("liste moi tous les tickets")


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


def test_hash_row_resolution(db):
    user = User(
        email="tix@test.com",
        password_hash="x",
        full_name="Tix",
        role="client",
        status="active",
        organization_id="org-tix-1",
    )
    db.add(user)
    db.flush()
    for tid, subj in ((11, "A"), (10, "B")):
        db.add(
            SupportTicket(
                id=tid,
                user_id=user.id,
                subject=subj,
                message="msg " * 3,
                status="open",
            )
        )
    db.commit()

    hist = (
        "**Liste des tickets support**\n"
        "| 11 | SUP-11 | A | a@b.com | open | medium |\n"
        "| 10 | SUP-10 | B | a@b.com | open | low |"
    )
    assert resolve_ticket_id_from_context(db, 1, history_text=hist) == 11
    assert resolve_ticket_id_from_context(db, 2, history_text=hist) == 10
    assert resolve_ticket_id_from_context(db, 11, history_text=hist) == 11


def test_hash_row_two_after_list(db):
    """#2 = 2e ligne du tableau, pas l'id PostgreSQL 2."""
    user = User(
        email="tix2@test.com",
        password_hash="x",
        full_name="Tix2",
        role="client",
        status="active",
        organization_id="org-tix-2",
    )
    db.add(user)
    db.flush()
    for tid, subj in ((11, "A"), (10, "B")):
        db.add(
            SupportTicket(
                id=tid,
                user_id=user.id,
                subject=subj,
                message="msg " * 3,
                status="open",
            )
        )
    db.commit()

    hist = (
        "**Liste des tickets support**\n"
        "| 11 | SUP-11 | A | a@b.com | open | medium |\n"
        "| 10 | SUP-10 | B | a@b.com | open | low |"
    )
    from app.services.admin_client.tickets.tickets_followup import extract_ticket_ref

    assert extract_ticket_ref("donne moi detaille du ticket #2", history_text=hist) == 10
    plan = classify_tickets_intent("donne moi detaille du ticket #2", history_text=hist)
    assert plan.task_type == TicketsTaskType.ticket_detail
    assert plan.ticket_id == 10


def test_ordinal_second_ticket_without_ticket_word():
    from app.services.admin_client.tickets.tickets_followup import extract_ticket_ref

    hist = (
        "**Liste des tickets support**\n"
        "| 11 | SUP-11 | A | a@b.com | open | medium |\n"
        "| 10 | SUP-10 | B | a@b.com | open | low |"
    )
    assert extract_ticket_ref("donne moi detaille de 2eme ticket", history_text=hist) == 10
    assert extract_ticket_ref("detaille du 2eme", history_text=hist) == 10
