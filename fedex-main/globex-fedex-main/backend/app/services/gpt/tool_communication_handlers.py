"""Handlers outils communication — notifications in-app, emails SMTP, users."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select

from app.models.user import User, UserRole, UserStatus
from app.services.activity_log_service import write_log
from app.services.email_service import is_email_configured, send_email
from app.services.employee_notification_service import create_employee_notification
from app.services.gpt.tool_handlers import _err, _ok
from app.services.gpt.tool_types import ToolExecutionContext, ToolResult
from app.services.notifications_service import _upsert as upsert_platform_notification
from app.services.user_notification_service import create_user_notification

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _resolve_user(ctx: ToolExecutionContext, args: dict[str, Any]) -> User | None:
    uid = args.get("user_id")
    email = str(args.get("email") or "").strip()
    if uid:
        return ctx.db.get(User, int(uid))
    if email:
        return ctx.db.scalar(select(User).where(User.email == email))
    return None


def _handle_notify_admin(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title") or "Alerte Globex").strip()[:200]
    message = str(args.get("message") or "").strip()
    if not message:
        return _err("notify_admin", "Message requis.")
    priority = str(args.get("priority") or "normal").lower()
    category = str(args.get("category") or "ia").lower()
    key = str(args.get("external_key") or f"globex-admin-{title[:40]}-{ctx.user_id}")
    upsert_platform_notification(
        ctx.db,
        external_key=key,
        category=category,
        title=title,
        message=message[:500],
        priority=priority if priority in {"low", "normal", "high", "critical"} else "normal",
        icon=str(args.get("icon") or "bell"),
        action_type=str(args.get("action_type") or ""),
        action_ref=str(args.get("action_ref") or ""),
    )
    ctx.db.flush()
    return _ok("notify_admin", title=title, notified=True, action_executed=True)


def _handle_notify_admin_task_complete(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    task = str(args.get("task") or args.get("title") or "Tâche agent").strip()
    summary = str(args.get("summary") or args.get("message") or "Terminé.").strip()
    return _handle_notify_admin(
        ctx,
        {
            "title": f"✓ {task[:120]}",
            "message": summary,
            "priority": args.get("priority") or "normal",
            "category": "ia",
            "external_key": args.get("external_key"),
        },
    )


def _handle_notify_user(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    user = _resolve_user(ctx, args)
    if user is None:
        return _err("notify_user", "Utilisateur introuvable (user_id ou email requis).")
    title = str(args.get("title") or "Message Globex").strip()[:200]
    message = str(args.get("message") or "").strip()
    if not message:
        return _err("notify_user", "Message requis.")
    ntype = str(args.get("type") or "system_alert")
    create_user_notification(
        ctx.db,
        user_id=user.id,
        type=ntype,
        title=title,
        message=message[:2000],
        sender_id=ctx.actor_admin_id,
        sender_role="admin",
        priority=str(args.get("priority") or "medium"),
        related_ticket_id=args.get("ticket_id"),
        related_tracking_number=str(args.get("tracking_number") or ""),
        link=str(args.get("link") or "/notifications"),
    )
    write_log(
        ctx.db,
        action="admin.notify_user",
        message=f"Notification envoyée à {user.email}",
        category="admin",
        level="INFO",
        user_id=user.id,
        actor_user_id=ctx.actor_admin_id,
        commit=False,
    )
    ctx.db.flush()
    return _ok(
        "notify_user",
        user_id=user.id,
        email=user.email,
        action_executed=True,
        task_answer=f"C'est envoyé — **{(user.full_name or '').strip() or user.email.split('@')[0].title()}** a reçu la notification sur son espace Globex.",
    )


def _handle_notify_user_warning(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    merged = {**args, "type": "security_alert", "priority": args.get("priority") or "high"}
    if not merged.get("title"):
        merged["title"] = "Avertissement administrateur"
    return _handle_notify_user(ctx, merged)


def _handle_notify_employee(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    user = _resolve_user(ctx, args)
    if user is None:
        return _err("notify_employee", "Employé introuvable.")
    if user.role != UserRole.employe.value:
        return _err("notify_employee", "L'utilisateur cible n'est pas un employé.")
    title = str(args.get("title") or "Message admin").strip()[:200]
    message = str(args.get("message") or "").strip()
    if not message:
        return _err("notify_employee", "Message requis.")
    create_employee_notification(
        ctx.db,
        employee_id=user.id,
        type=str(args.get("type") or "admin_message"),
        title=title,
        message=message[:2000],
        sender_id=ctx.actor_admin_id,
        sender_role="admin",
        priority=str(args.get("priority") or "medium"),
        link=str(args.get("link") or "/employee/notifications"),
    )
    ctx.db.flush()
    return _ok("notify_employee", user_id=user.id, action_executed=True)


def _handle_send_email(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    to = str(args.get("to") or args.get("email") or "").strip()
    if not to:
        user = _resolve_user(ctx, args)
        to = user.email if user else ""
    if not to or not _EMAIL_RE.match(to):
        return _err("send_email", "Destinataire e-mail invalide.")
    subject = str(args.get("subject") or "Message Globex FedEx").strip()[:200]
    body = str(args.get("body") or args.get("text") or args.get("message") or "").strip()
    if not body:
        return _err("send_email", "Corps du message requis.")
    if not is_email_configured():
        return _err("send_email", "SMTP non configuré sur le serveur FedEx.")
    sent = send_email(to=to, subject=subject, body_text=body)
    if not sent:
        return _err("send_email", "Échec envoi SMTP.")
    write_log(
        ctx.db,
        action="admin.send_email",
        message=f"E-mail envoyé à {to} — {subject[:80]}",
        category="admin",
        level="INFO",
        actor_user_id=ctx.actor_admin_id,
        commit=False,
    )
    ctx.db.flush()
    display = to.split("@")[0].replace(".", " ").title()
    return _ok(
        "send_email",
        to=to,
        subject=subject,
        email_sent=True,
        action_executed=True,
        task_answer=f"C'est fait — le mail « {subject} » est parti pour **{display}** ({to}).",
    )


def _handle_send_client_email(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    user = _resolve_user(ctx, args)
    to = str(args.get("to") or args.get("email") or (user.email if user else "")).strip()
    if not to:
        return _err("send_client_email", "Destinataire requis.")
    subject = str(args.get("subject") or "Information concernant votre expédition").strip()
    body = str(args.get("body") or args.get("text") or args.get("message") or "").strip()
    if not body:
        return _err("send_client_email", "Corps du message requis.")
    sent = _handle_send_email(ctx, {"to": to, "subject": subject, "body": body})
    if not sent.success:
        return _err("send_client_email", sent.error or "Échec envoi SMTP.")
    if user and (user.full_name or "").strip():
        display = user.full_name.strip()
    else:
        display = to.split("@")[0].replace(".", " ").title()
    subject_l = subject.lower()
    if "remerciement" in subject_l or "merci" in subject_l:
        task_answer = (
            f"C'est envoyé — j'ai fait partir un mail de remerciement à **{display}** ({to}). "
            f"Il devrait le recevoir d'ici quelques minutes."
        )
    else:
        task_answer = (
            f"C'est fait — le mail « {subject} » est parti pour **{display}** ({to})."
        )
    return _ok(
        "send_client_email",
        to=to,
        email=to,
        subject=subject,
        email_sent=True,
        action_executed=True,
        task_answer=task_answer,
    )


def _handle_draft_client_email(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    to = str(args.get("to") or args.get("email") or "").strip()
    subject = str(args.get("subject") or "Brouillon — information client").strip()
    body = str(args.get("body") or args.get("text") or args.get("message") or "").strip()
    return _ok(
        "draft_client_email",
        to=to,
        subject=subject,
        body=body,
        draft=True,
        analysis_only=True,
    )


def _handle_search_users(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    q = str(args.get("query") or args.get("q") or args.get("email") or "").strip()
    if not q:
        return _err("search_users", "Requête de recherche requise.")
    limit = min(max(int(args.get("limit") or 20), 1), 50)
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q.isdigit():
        stmt = stmt.where(or_(User.id == int(q), User.email.ilike(f"%{q}%")))
    else:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(like),
                User.full_name.ilike(like),
            )
        )
    rows = list(ctx.db.scalars(stmt).all())
    users = [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name or "",
            "role": u.role,
            "status": u.status,
        }
        for u in rows
    ]
    return _ok("search_users", query=q, count=len(users), users=users)


def _execute_suspend_reactivate(
    ctx: ToolExecutionContext,
    args: dict[str, Any],
    *,
    action: str,
) -> ToolResult:
    from app.services.security_ids_service import reactivate_user, suspend_user

    user = _resolve_user(ctx, args)
    if user is None:
        return _err(action, "Utilisateur introuvable.")
    if user.role == UserRole.admin.value:
        return _err(action, "Impossible sur un compte administrateur.")
    admin_id = ctx.actor_admin_id or ctx.user_id
    reason = str(args.get("reason") or "Action admin Globex OS")[:500]
    if action == "suspend_user":
        ok = suspend_user(ctx.db, user.id, reason=reason, actor_admin_id=admin_id)
        label = "suspendu"
    else:
        ok = reactivate_user(ctx.db, user.id, actor_admin_id=admin_id)
        label = "réactivé"
    if not ok:
        return _err(action, f"Échec — compte {user.email} peut-être déjà dans l'état cible.")
    return _ok(
        action,
        user_id=user.id,
        email=user.email,
        status_after=user.status,
        action_executed=True,
        task_answer=f"FAIT — Compte {user.email} (#{user.id}) {label}.",
    )


COMMUNICATION_HANDLERS: dict[str, Any] = {
    "notify_admin": _handle_notify_admin,
    "notify_admin_task_complete": _handle_notify_admin_task_complete,
    "notify_user": _handle_notify_user,
    "notify_user_warning": _handle_notify_user_warning,
    "notify_employee": _handle_notify_employee,
    "send_email": _handle_send_email,
    "send_client_email": _handle_send_client_email,
    "draft_client_email": _handle_draft_client_email,
    "search_users": _handle_search_users,
}
