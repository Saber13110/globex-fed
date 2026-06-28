"""Handlers outils Phase 5 — composites, workspace, modération utilisateurs."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.support_ticket import SupportTicket
from app.models.user import User, UserRole, UserStatus
from app.services.activity_log_service import write_log
from app.services.email_service import is_email_configured, send_email
from app.services.gpt.tool_handlers import _approval_action, _err, _handle_analyze_security, _ok
from app.services.gpt.tool_types import ToolExecutionContext, ToolResult
from app.services.notifications_service import _upsert as upsert_platform_notification


def _composite(ctx: ToolExecutionContext, tool_name: str, args: dict[str, Any]) -> ToolResult:
    from app.services.ai_assistant.composite_tools import run_composite_tool

    payload = run_composite_tool(ctx, tool_name, args)
    if payload.get("status") == "error":
        return _err(tool_name, str(payload.get("error") or "Échec composite."))
    return _ok(tool_name, **payload)


def _handle_analyze_platform_health(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _composite(ctx, "analyze_platform_health", args)


def _handle_generate_security_report(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _composite(ctx, "generate_security_report", args)


def _handle_get_agent_missions_summary(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _composite(ctx, "get_agent_missions_summary", args)


def _handle_analyze_weekly_activity(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _composite(ctx, "analyze_weekly_activity", args)


def _handle_get_security_alerts(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    merged = {
        "status": args.get("status") or "open",
        "limit": args.get("limit") or 20,
    }
    result = _handle_analyze_security(ctx, merged)
    if result.success and result.data:
        result.data["alias_of"] = "analyze_security"
    return result


def _handle_get_workspace_briefing(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.globex_agent.workspace_bridge import build_workspace_overview

    admin = ctx.db.get(User, ctx.actor_admin_id or ctx.user_id)
    if admin is None:
        return _err("get_workspace_briefing", "Admin introuvable.")
    overview = build_workspace_overview(ctx.db, admin)
    lines = overview.get("briefing_lines") or []
    return _ok(
        "get_workspace_briefing",
        signals=overview.get("signals") or {},
        briefing_lines=lines,
        briefing_text="\n".join(f"• {line}" for line in lines),
        sla_breaches=overview.get("sla_breaches") or [],
        dormant_accounts=overview.get("dormant_accounts") or [],
    )


def _handle_push_jarvis_alert(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title") or "Alerte Jarvis").strip()[:200]
    message = str(args.get("message") or "").strip()
    if not message:
        return _err("push_jarvis_alert", "Message requis.")
    level = str(args.get("level") or args.get("priority") or "high").lower()
    priority = level if level in {"low", "normal", "high", "critical"} else "high"
    key = str(args.get("external_key") or f"jarvis-alert-{title[:40]}-{ctx.user_id}")
    upsert_platform_notification(
        ctx.db,
        external_key=key,
        category="jarvis",
        title=title,
        message=message[:500],
        priority=priority,
        icon=str(args.get("icon") or "cpu"),
        action_type=str(args.get("action_type") or "open_workspace"),
        action_ref=str(args.get("action_ref") or "/dashboard"),
    )
    ctx.db.flush()
    return _ok(
        "push_jarvis_alert",
        title=title,
        priority=priority,
        pushed=True,
        action_executed=True,
        task_answer=f"Alerte Jarvis publiée — **{title}**.",
    )


def _handle_send_admin_email(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    subject = str(args.get("subject") or "Message Globex Admin").strip()
    body = str(args.get("body") or args.get("message") or "").strip()
    if not body:
        return _err("send_admin_email", "Corps du message requis.")
    if not _can_execute(ctx, args):
        return _approval_action("send_admin_email", args, label="e-mail aux administrateurs")
    if not is_email_configured():
        return _err("send_admin_email", "SMTP non configuré.")
    admins = list(
        ctx.db.scalars(
            select(User).where(User.role == UserRole.admin.value, User.status == UserStatus.active.value)
        ).all()
    )
    if not admins:
        return _err("send_admin_email", "Aucun administrateur actif trouvé.")
    sent = 0
    for admin in admins:
        try:
            send_email(to=admin.email, subject=subject, body_text=body)
            sent += 1
        except Exception:
            continue
    if not sent:
        return _err("send_admin_email", "Échec envoi SMTP.")
    return _ok(
        "send_admin_email",
        recipients=sent,
        action_executed=True,
        task_answer=f"C'est envoyé — e-mail transmis à {sent} administrateur(s).",
    )


def _can_execute(ctx: ToolExecutionContext, args: dict[str, Any]) -> bool:
    return bool(args.get("_skip_approval") or ctx.admin_direct_order or ctx.skip_approval)


def _handle_delete_user(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    if not _can_execute(ctx, args):
        return _approval_action("delete_user", args, label="suppression compte utilisateur")
    uid = args.get("user_id")
    email = str(args.get("email") or "").strip().lower()
    user: User | None = None
    if uid:
        user = ctx.db.get(User, int(uid))
    elif email:
        user = ctx.db.scalar(select(User).where(User.email == email))
    if user is None:
        return _err("delete_user", "Utilisateur introuvable.")
    actor_id = ctx.actor_admin_id or ctx.user_id
    if user.id == actor_id:
        return _err("delete_user", "Impossible de supprimer votre propre compte.")
    if user.role == UserRole.admin.value:
        admins = int(
            ctx.db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin.value)) or 0
        )
        if admins <= 1:
            return _err("delete_user", "Impossible de supprimer le dernier administrateur.")
    target_email = user.email
    write_log(
        ctx.db,
        action="admin.user_delete",
        message=f"Utilisateur supprimé par agent Globex : {target_email}",
        category="admin",
        level="WARNING",
        user_id=user.id,
        actor_user_id=actor_id,
        metadata={"role": user.role, "status": user.status, "source": "globex_agent"},
        commit=False,
    )
    ctx.db.delete(user)
    ctx.db.flush()
    return _ok(
        "delete_user",
        user_id=user.id,
        email=target_email,
        action_executed=True,
        task_answer=f"FAIT — Compte **{target_email}** supprimé définitivement.",
    )


def _resolve_ticket(ctx: ToolExecutionContext, args: dict[str, Any]) -> SupportTicket | None:
    tid = args.get("ticket_id")
    if tid:
        return ctx.db.get(SupportTicket, int(tid))
    number = str(args.get("ticket_number") or "").strip()
    if number:
        return ctx.db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == number))
    return None


def _handle_assign_ticket(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    if not _can_execute(ctx, args):
        return _approval_action("assign_ticket", args, label="assignation ticket")
    ticket = _resolve_ticket(ctx, args)
    if ticket is None:
        return _err("assign_ticket", "Ticket introuvable.")
    assignee = str(args.get("assignee") or args.get("agent") or "équipe support").strip()
    note = str(args.get("note") or f"Assigné à {assignee}").strip()[:500]
    ticket.admin_note = note
    ctx.db.flush()
    return _ok(
        "assign_ticket",
        ticket_id=ticket.id,
        assignee=assignee,
        action_executed=True,
        task_answer=f"FAIT — Ticket #{ticket.id} assigné à **{assignee}**.",
    )


def _handle_update_ticket_priority(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    if not _can_execute(ctx, args):
        return _approval_action("update_ticket_priority", args, label="changement priorité ticket")
    ticket = _resolve_ticket(ctx, args)
    if ticket is None:
        return _err("update_ticket_priority", "Ticket introuvable.")
    priority = str(args.get("priority") or "high").strip().lower()
    if priority not in {"low", "medium", "high", "urgent", "critical"}:
        return _err("update_ticket_priority", "Priorité invalide.")
    old = ticket.priority
    ticket.priority = priority
    ctx.db.flush()
    return _ok(
        "update_ticket_priority",
        ticket_id=ticket.id,
        priority_before=old,
        priority_after=priority,
        action_executed=True,
        task_answer=f"FAIT — Ticket #{ticket.id} : priorité **{old}** → **{priority}**.",
    )


def _handle_invite_user(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    if not _can_execute(ctx, args):
        return _approval_action("invite_user", args, label="invitation utilisateur")
    email = str(args.get("email") or "").strip().lower()
    full_name = str(args.get("full_name") or args.get("name") or email.split("@")[0]).strip()
    role = str(args.get("role") or UserRole.client.value).strip().lower()
    if not email:
        return _err("invite_user", "Email requis.")
    if role not in {UserRole.client.value, UserRole.employe.value, UserRole.admin.value}:
        return _err("invite_user", "Rôle invalide.")
    existing = ctx.db.scalar(select(User.id).where(User.email == email))
    if existing:
        return _err("invite_user", "Un compte existe déjà avec cet email.")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    user = User(
        full_name=full_name,
        email=email,
        password_hash=get_password_hash(secrets.token_urlsafe(24)),
        role=role,
        status=UserStatus.invited.value,
        activation_token=token,
        activation_expires_at=expires,
        preferred_language=str(args.get("preferred_language") or "fr"),
        organization_id=secrets.token_hex(16),
    )
    ctx.db.add(user)
    ctx.db.flush()
    email_sent = False
    settings = get_settings()
    activate_url = f"{settings.frontend_base_url.rstrip('/')}/activate?token={token}"
    if is_email_configured():
        try:
            send_email(
                to=email,
                subject="Invitation — Globex FedEx Platform",
                body_text=(
                    f"Bonjour {full_name},\n\n"
                    f"Vous avez été invité(e) sur Globex FedEx en tant que {role}.\n"
                    f"Activez votre compte : {activate_url}\n"
                ),
            )
            email_sent = True
        except Exception:
            email_sent = False
    write_log(
        ctx.db,
        action="admin.user_invite",
        message=f"Invitation envoyée à {email}",
        category="admin",
        level="INFO",
        user_id=user.id,
        actor_user_id=ctx.actor_admin_id or ctx.user_id,
        metadata={"role": role, "email_sent": email_sent, "source": "globex_agent"},
        commit=False,
    )
    ctx.db.flush()
    return _ok(
        "invite_user",
        user_id=user.id,
        email=email,
        role=role,
        email_sent=email_sent,
        action_executed=True,
        task_answer=(
            f"FAIT — Invitation créée pour **{email}** ({role})."
            + (" E-mail d'activation envoyé." if email_sent else " SMTP indisponible — lien à transmettre manuellement.")
        ),
    )


EXTENDED_HANDLERS: dict[str, Any] = {
    "analyze_platform_health": _handle_analyze_platform_health,
    "generate_security_report": _handle_generate_security_report,
    "get_agent_missions_summary": _handle_get_agent_missions_summary,
    "analyze_weekly_activity": _handle_analyze_weekly_activity,
    "get_security_alerts": _handle_get_security_alerts,
    "get_workspace_briefing": _handle_get_workspace_briefing,
    "push_jarvis_alert": _handle_push_jarvis_alert,
    "send_admin_email": _handle_send_admin_email,
    "delete_user": _handle_delete_user,
    "assign_ticket": _handle_assign_ticket,
    "update_ticket_priority": _handle_update_ticket_priority,
    "invite_user": _handle_invite_user,
}
