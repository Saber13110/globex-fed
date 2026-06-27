"""Handlers outils tickets support — fermeture, escalade, brouillon."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.platform_notification import PlatformNotification
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.services.activity_log_service import write_log
from app.services.gpt.tool_handlers import _approval_action, _err, _ok
from app.services.gpt.tool_types import ToolExecutionContext, ToolResult
from app.services.globex_agent.ticket_sla_service import scan_sla_breaches


def _get_ticket(db: Session, ticket_id: int) -> SupportTicket | None:
    return db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages))
        .where(SupportTicket.id == ticket_id)
    )


def _can_execute(ctx: ToolExecutionContext, args: dict[str, Any]) -> bool:
    return bool(args.get("_skip_approval") or ctx.admin_direct_order or ctx.skip_approval)


def close_ticket_admin(
    db: Session,
    *,
    ticket_id: int,
    admin_id: int,
    resolution_note: str = "",
) -> tuple[bool, dict[str, Any]]:
    ticket = _get_ticket(db, ticket_id)
    if not ticket:
        return False, {"error": "ticket_not_found"}
    if ticket.status == SupportTicketStatus.closed:
        return False, {"error": "already_closed"}
    ticket.status = SupportTicketStatus.closed
    if resolution_note:
        ticket.admin_note = resolution_note[:500]
    write_log(
        db,
        action="support.admin_close",
        message=f"Ticket #{ticket.id} fermé par admin/agent",
        category="admin",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=admin_id,
        metadata={"ticket_id": ticket.id, "source": "globex_agent"},
        commit=False,
    )
    db.flush()
    return True, {
        "ticket_id": ticket.id,
        "status_after": ticket.status,
        "subject": ticket.subject,
    }


def escalate_ticket_admin(
    db: Session,
    *,
    ticket_id: int,
    admin_id: int,
    reason: str = "",
) -> tuple[bool, dict[str, Any]]:
    ticket = _get_ticket(db, ticket_id)
    if not ticket:
        return False, {"error": "ticket_not_found"}
    if ticket.status == SupportTicketStatus.closed:
        return False, {"error": "ticket_closed"}
    ticket.status = "escalated"
    if str(ticket.priority or "").lower() not in {"high", "urgent", "critical"}:
        ticket.priority = "high"
    if reason:
        ticket.admin_note = reason[:500]
    key = f"support-escalated-{ticket.id}"
    exists = db.scalar(select(PlatformNotification.id).where(PlatformNotification.external_key == key))
    if not exists:
        db.add(
            PlatformNotification(
                external_key=key,
                category="incidents",
                title="Ticket escaladé",
                message=f"Ticket #{ticket.id} — {ticket.subject}",
                route=f"/admin?section=notifications&ticket={ticket.id}",
                priority="high",
                channel="web",
                icon="alert-triangle",
                action_label="Voir",
                action_type="support_ticket",
                action_ref=str(ticket.id),
            )
        )
    write_log(
        db,
        action="support.admin_escalate",
        message=f"Ticket #{ticket.id} escaladé",
        category="admin",
        level="WARNING",
        user_id=ticket.user_id,
        actor_user_id=admin_id,
        metadata={"ticket_id": ticket.id, "reason": reason[:200], "source": "globex_agent"},
        commit=False,
    )
    db.flush()
    return True, {
        "ticket_id": ticket.id,
        "status_after": ticket.status,
        "priority_after": ticket.priority,
        "subject": ticket.subject,
    }


def _handle_close_ticket(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    ticket_id = args.get("ticket_id")
    if not ticket_id:
        return _err("close_ticket", "ticket_id requis.")
    if not _can_execute(ctx, args):
        return _approval_action("close_ticket", args, label=f"fermeture ticket #{ticket_id}")
    admin_id = ctx.actor_admin_id or ctx.user_id
    note = str(args.get("resolution_note") or args.get("note") or "").strip()
    ok, verification = close_ticket_admin(
        ctx.db, ticket_id=int(ticket_id), admin_id=admin_id, resolution_note=note,
    )
    if not ok:
        return _err("close_ticket", str(verification.get("error") or "échec fermeture"))
    ctx.db.commit()
    return _ok(
        "close_ticket",
        ticket_id=int(ticket_id),
        verification=verification,
        action_executed=True,
        task_answer=f"FAIT — Ticket #{ticket_id} fermé.",
    )


def _handle_escalate_ticket(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    ticket_id = args.get("ticket_id")
    if not ticket_id:
        return _err("escalate_ticket", "ticket_id requis.")
    if not _can_execute(ctx, args):
        return _approval_action("escalate_ticket", args, label=f"escalade ticket #{ticket_id}")
    admin_id = ctx.actor_admin_id or ctx.user_id
    reason = str(args.get("reason") or args.get("note") or "").strip()
    ok, verification = escalate_ticket_admin(
        ctx.db, ticket_id=int(ticket_id), admin_id=admin_id, reason=reason,
    )
    if not ok:
        return _err("escalate_ticket", str(verification.get("error") or "échec escalade"))
    ctx.db.commit()
    return _ok(
        "escalate_ticket",
        ticket_id=int(ticket_id),
        verification=verification,
        action_executed=True,
        task_answer=f"FAIT — Ticket #{ticket_id} escaladé (priorité haute).",
    )


def _handle_draft_ticket_reply(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    ticket_id = args.get("ticket_id")
    body = str(args.get("reply_body") or args.get("body") or args.get("draft") or "").strip()
    if not ticket_id:
        return _err("draft_ticket_reply", "ticket_id requis.")
    ticket = _get_ticket(ctx.db, int(ticket_id))
    if not ticket:
        return _err("draft_ticket_reply", "Ticket introuvable.")
    if not body:
        body = (
            f"Bonjour,\n\nConcernant votre demande « {ticket.subject} », "
            "nous traitons votre dossier et reviendrons vers vous rapidement.\n\n"
            "Cordialement,\nSupport Globex FedEx"
        )
    return _ok(
        "draft_ticket_reply",
        ticket_id=int(ticket_id),
        subject=ticket.subject,
        draft_body=body,
        draft=True,
        analysis_only=True,
    )


def _handle_scan_ticket_sla(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    limit = min(max(int(args.get("limit") or 15), 1), 30)
    breaches = scan_sla_breaches(ctx.db, limit=limit)
    return _ok(
        "scan_ticket_sla",
        breach_count=len(breaches),
        breaches=breaches,
        task_answer=(
            f"{len(breaches)} ticket(s) hors SLA."
            if breaches
            else "Aucun ticket hors SLA pour le moment."
        ),
    )


TICKET_HANDLERS = {
    "close_ticket": _handle_close_ticket,
    "escalate_ticket": _handle_escalate_ticket,
    "draft_ticket_reply": _handle_draft_ticket_reply,
    "scan_ticket_sla": _handle_scan_ticket_sla,
}
