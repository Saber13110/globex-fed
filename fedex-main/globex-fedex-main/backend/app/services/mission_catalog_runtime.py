"""Exécution déterministe des tâches catalogue Support / Users (missions workflow)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.mission_chain_context import resolve_user_id_from_chain
from app.services.mission_task_runner import (
    split_prior_context,
    support_plan_for_catalog_task,
    users_plan_for_catalog_task,
)


def _mission_chain_from_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    ctx: dict[str, Any] = {"ticket_id": int(ticket["id"])}
    if ticket.get("user_id") is not None:
        ctx["user_id"] = int(ticket["user_id"])
    if ticket.get("user_email"):
        ctx["user_email"] = str(ticket["user_email"])
    return ctx


def _mission_chain_from_tickets(tickets: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [int(t["id"]) for t in tickets if isinstance(t, dict) and t.get("id") is not None]
    ctx: dict[str, Any] = {}
    if ids:
        ctx["ticket_ids"] = ids
    if len(tickets) == 1:
        ctx.update(_mission_chain_from_ticket(tickets[0]))
    return ctx


def execute_support_catalog_task(
    db: Session,
    task: str,
    catalog_task_id: str | None,
    *,
    limit: int = 30,
) -> dict[str, Any] | None:
    """Compose déterministe tickets — retourne None si pas de routage catalogue."""
    plan = support_plan_for_catalog_task(catalog_task_id, limit=limit)
    if plan is None:
        return None

    from app.services.admin_client.tickets.tickets_compose import compose_tickets_response
    from app.services.admin_client.tickets.tickets_intent import resolve_target_ticket
    from app.services.admin_client.tickets.tickets_pipeline import execute_tools
    from app.services.admin_client.tickets.tickets_reconcile import reconcile_tickets_plan
    from app.services.admin_client.tickets.tickets_types import TicketsTaskType

    user_part, prior = split_prior_context(task)
    merged = (user_part or task).strip()
    history = (prior or "").strip()

    plan = reconcile_tickets_plan(merged, plan, history_text=history)

    write_tasks = {TicketsTaskType.ticket_reply, TicketsTaskType.ticket_resolve}
    needs_ticket = plan.task_type in {TicketsTaskType.ticket_detail, *write_tasks}

    if needs_ticket:
        resolution = resolve_target_ticket(db, merged, plan, history_text=history, lang="fr")
        if resolution.needs_clarification:
            q = resolution.clarification_question or "Quel ticket ciblez-vous ?"
            return {
                "task_answer": q,
                "analysis": q,
                "needs_clarification": True,
                "deterministic_compose": True,
            }
        if resolution.ticket_id:
            plan.ticket_id = resolution.ticket_id

    executed = execute_tools(db, plan)
    if not executed.ok:
        err = executed.error or "fetch_failed"
        msg = (
            "NON FAIT — Impossible de récupérer les tickets support.\n"
            f"Détail : {err}"
        )
        return {"task_answer": msg, "analysis": msg, "deterministic_compose": True}

    answer = compose_tickets_response(executed.processed, plan, lang="fr")
    output: dict[str, Any] = {
        "task_answer": answer,
        "analysis": answer,
        "deterministic_compose": True,
        "analysis_only": True,
    }

    ticket = executed.processed.get("ticket")
    if isinstance(ticket, dict) and ticket.get("id") is not None:
        output["target_ticket"] = {
            "ticket_id": int(ticket["id"]),
            "ticket_number": ticket.get("ticket_number"),
            "subject": ticket.get("subject"),
            "status": ticket.get("status"),
        }
        output["chain_context"] = _mission_chain_from_ticket(ticket)
    else:
        tickets = executed.processed.get("tickets") or []
        if tickets:
            output["chain_context"] = _mission_chain_from_tickets(tickets)

    return output


def execute_users_catalog_task(
    db: Session,
    task: str,
    catalog_task_id: str | None,
    *,
    limit: int = 30,
    chain_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compose déterministe utilisateurs — retourne None si pas de routage catalogue."""
    plan = users_plan_for_catalog_task(catalog_task_id, limit=limit)
    if plan is None:
        return None

    from app.services.admin_client.users.users_compose import compose_users_response
    from app.services.admin_client.users.users_intent import resolve_target_user
    from app.services.admin_client.users.users_pipeline import execute_tools
    from app.services.admin_client.users.users_reconcile import reconcile_users_plan
    from app.services.admin_client.users.users_types import UsersTaskType

    ctx = dict(chain_context or {})
    user_part, prior = split_prior_context(task)
    merged = (user_part or task).strip()
    history = (prior or "").strip()
    if history:
        history = f"{history}\n{merged}"

    plan = reconcile_users_plan(merged, plan, history_text=history)

    write_tasks = {
        UsersTaskType.user_suspend,
        UsersTaskType.user_reactivate,
        UsersTaskType.user_delete,
        UsersTaskType.user_update_name,
        UsersTaskType.user_reset_password,
    }

    if plan.task_type != UsersTaskType.user_list:
        uid_chain = resolve_user_id_from_chain(db, ctx)
        if uid_chain:
            plan.user_id = uid_chain
        else:
            resolution = resolve_target_user(db, merged, plan, history_text=history, lang="fr")
            if resolution.needs_clarification and not resolution.user_id:
                q = resolution.clarification_question or (
                    "Quel utilisateur ciblez-vous (e-mail, #id ou client du ticket précédent) ?"
                )
                return {
                    "task_answer": q,
                    "analysis": q,
                    "needs_clarification": True,
                    "deterministic_compose": True,
                }
            if resolution.user_id:
                plan.user_id = resolution.user_id

    if plan.task_type in write_tasks:
        return None

    executed = execute_tools(db, plan, lang="fr")
    if not executed.ok:
        err = executed.error or "fetch_failed"
        msg = (
            "NON FAIT — Impossible de récupérer les données utilisateur.\n"
            f"Détail : {err}"
        )
        return {"task_answer": msg, "analysis": msg, "deterministic_compose": True}

    answer = compose_users_response(executed.processed, plan, lang="fr")
    output: dict[str, Any] = {
        "task_answer": answer,
        "analysis": answer,
        "deterministic_compose": True,
        "analysis_only": True,
    }

    user = executed.processed.get("user")
    if isinstance(user, dict) and user.get("id") is not None:
        output["target_user"] = {
            "user_id": int(user["id"]),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "status": user.get("status"),
        }
        chain_out: dict[str, Any] = {"user_id": int(user["id"])}
        if user.get("email"):
            chain_out["user_email"] = str(user["email"])
        output["chain_context"] = chain_out

    return output
