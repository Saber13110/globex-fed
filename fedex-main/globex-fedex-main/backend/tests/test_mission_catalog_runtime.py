"""Tests — routage catalogue Support / Users en mission."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.admin_client.tickets.tickets_followup import list_ticket_ids_from_history
from app.services.mission_chain_context import resolve_user_id_from_chain
from app.services.mission_task_handoff import validate_task_handoff
from app.services.mission_task_runner import support_plan_for_catalog_task, users_plan_for_catalog_task


def test_list_ticket_ids_from_bullet_mission_format():
    text = "Tickets (open) — 1 trouvé(s) :\n- #11 [open] Blocage douane"
    assert list_ticket_ids_from_history(text) == [11]


def test_support_ticket_detail_plan():
    plan = support_plan_for_catalog_task("ticket_detail")
    assert plan is not None
    assert plan.task_type.value == "ticket_detail"


def test_users_logs_plan():
    plan = users_plan_for_catalog_task("user_logs")
    assert plan is not None
    assert plan.task_type.value == "user_logs"


def test_ticket_detail_to_user_logs_allowed():
    assert (
        validate_task_handoff(
            "support",
            "ticket_detail",
            "users",
            "user_logs",
            has_prior_output=True,
        )
        is None
    )


@patch("app.services.admin_client.tickets.tickets_tool.get_ticket_detail")
def test_resolve_user_from_ticket_chain(mock_get_detail):
    mock_get_detail.return_value = {"id": 11, "user_id": 42, "user_email": "amine@gmail.com"}
    db = MagicMock()
    uid = resolve_user_id_from_chain(db, {"ticket_id": 11})
    assert uid == 42


@patch("app.services.admin_client.tickets.tickets_pipeline.execute_tools")
@patch("app.services.admin_client.tickets.tickets_compose.compose_tickets_response")
@patch("app.services.admin_client.tickets.tickets_intent.resolve_target_ticket")
@patch("app.services.admin_client.tickets.tickets_reconcile.reconcile_tickets_plan")
def test_support_catalog_ticket_detail(mock_reconcile, mock_resolve, mock_compose, mock_exec):
    from app.services.admin_client.tickets.tickets_intent import TargetTicketResolution
    from app.services.admin_client.tickets.tickets_types import TicketsPlan, TicketsProfile, TicketsTaskType
    from app.services.mission_catalog_runtime import execute_support_catalog_task

    plan = TicketsPlan(task_type=TicketsTaskType.ticket_detail, profile=TicketsProfile.DETAIL)
    mock_reconcile.return_value = plan
    mock_resolve.return_value = TargetTicketResolution(ticket_id=11)
    mock_exec.return_value = MagicMock(
        ok=True,
        processed={
            "ticket": {
                "id": 11,
                "user_id": 5,
                "user_email": "amine@gmail.com",
                "subject": "Blocage douane",
                "status": "open",
            }
        },
        tools_called=["get_ticket_detail"],
    )
    mock_compose.return_value = "**Fiche ticket**\n#11 — Blocage douane"

    out = execute_support_catalog_task(
        MagicMock(),
        "Analyser en détail un ticket.\n\nPrécisions : amine@gmail.com",
        "ticket_detail",
    )
    assert out is not None
    assert out["deterministic_compose"] is True
    assert "Fiche ticket" in out["task_answer"]
    assert out["chain_context"]["user_email"] == "amine@gmail.com"


@patch("app.services.admin_client.users.users_pipeline.execute_tools")
@patch("app.services.admin_client.users.users_compose.compose_users_response")
@patch("app.services.admin_client.users.users_intent.resolve_target_user")
@patch("app.services.admin_client.users.users_reconcile.reconcile_users_plan")
def test_users_catalog_logs_from_ticket_context(mock_reconcile, mock_resolve, mock_compose, mock_exec):
    from app.services.admin_client.users.users_intent import TargetUserResolution
    from app.services.admin_client.users.users_types import UsersPlan, UsersProfile, UsersTaskType
    from app.services.mission_catalog_runtime import execute_users_catalog_task

    plan = UsersPlan(task_type=UsersTaskType.user_logs, profile=UsersProfile.LOGS)
    mock_reconcile.return_value = plan
    mock_resolve.return_value = TargetUserResolution()
    mock_exec.return_value = MagicMock(
        ok=True,
        processed={
            "user": {"id": 5, "email": "amine@gmail.com", "full_name": "Amine"},
            "logs": [{"created_at": "2026-06-15", "level": "INFO", "action": "login", "message": "Connexion"}],
            "logs_total": 1,
        },
        tools_called=["get_user_logs"],
    )
    mock_compose.return_value = "**Logs — #5 amine@gmail.com**\n\n- événement"

    with patch("app.services.mission_chain_context.resolve_user_id_from_chain", return_value=5):
        out = execute_users_catalog_task(
            MagicMock(),
            "Analyser l'activité récente d'un utilisateur.\n\n"
            "Contexte étape précédente (Support Agent) : - #11 [open] Blocage douane",
            "user_logs",
            chain_context={"ticket_id": 11},
        )
    assert out is not None
    assert out["deterministic_compose"] is True
    assert "Logs" in out["task_answer"]
    assert "Gemini" not in out["task_answer"]
