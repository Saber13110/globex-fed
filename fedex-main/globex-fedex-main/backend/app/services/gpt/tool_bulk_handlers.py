"""Handlers outils broadcast / bulk — Phase 3 Globex OS."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.user import User, UserRole, UserStatus
from app.services.activity_log_service import write_log
from app.services.email_service import is_email_configured, send_email
from app.services.globex_agent.dormant_accounts_service import scan_dormant_accounts
from app.services.gpt.tool_handlers import _err, _ok
from app.services.gpt.tool_types import ToolExecutionContext, ToolResult
from app.services.security_ids_service import suspend_user
from app.services.user_notification_service import create_user_notification

_BULK_LIMIT_DEFAULT = 100
_BULK_LIMIT_MAX = 500


def _clamp_limit(raw: Any) -> int:
    try:
        n = int(raw or _BULK_LIMIT_DEFAULT)
    except (TypeError, ValueError):
        n = _BULK_LIMIT_DEFAULT
    return min(max(n, 1), _BULK_LIMIT_MAX)


def _active_users_query(
    db,
    *,
    role: str | None = None,
    user_ids: list[int] | None = None,
    limit: int,
):
    stmt = (
        select(User)
        .where(
            User.status == UserStatus.active.value,
            User.role != UserRole.admin.value,
        )
        .order_by(User.id.asc())
        .limit(limit)
    )
    if role:
        stmt = stmt.where(User.role == role.lower().strip())
    if user_ids:
        stmt = select(User).where(User.id.in_(user_ids)).order_by(User.id.asc())
    return stmt


def _handle_scan_dormant_accounts(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    days = int(args.get("days") or 30)
    limit = min(max(int(args.get("limit") or 20), 1), 100)
    role = str(args.get("role") or "").strip() or None
    rows = scan_dormant_accounts(ctx.db, days=days, limit=limit, role=role)
    return _ok(
        "scan_dormant_accounts",
        count=len(rows),
        days_threshold=days,
        accounts=rows,
        analysis_only=True,
        task_answer=(
            f"{len(rows)} compte(s) inactif(s) depuis plus de {days} jours."
            if rows
            else f"Aucun compte inactif détecté sur les {days} derniers jours."
        ),
    )


def _handle_notify_users_by_role(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    role = str(args.get("role") or "client").strip().lower()
    title = str(args.get("title") or "Message Globex").strip()[:200]
    message = str(args.get("message") or "").strip()
    if not message:
        return _err("notify_users_by_role", "Message requis.")
    if role == UserRole.admin.value:
        return _err("notify_users_by_role", "Diffusion vers les admins interdite via cet outil.")
    limit = _clamp_limit(args.get("limit"))
    users = list(ctx.db.scalars(_active_users_query(ctx.db, role=role, limit=limit)).all())
    if not users:
        return _err("notify_users_by_role", f"Aucun utilisateur actif avec le rôle « {role} ».")

    sent = 0
    for user in users:
        create_user_notification(
            ctx.db,
            user_id=user.id,
            type=str(args.get("type") or "system_alert"),
            title=title,
            message=message[:2000],
            sender_id=ctx.actor_admin_id,
            sender_role="admin",
            priority=str(args.get("priority") or "medium"),
            link=str(args.get("link") or "/notifications"),
        )
        sent += 1
    ctx.db.flush()
    write_log(
        ctx.db,
        action="admin.notify_users_by_role",
        message=f"Notification rôle {role} — {sent} destinataire(s)",
        category="admin",
        level="INFO",
        actor_user_id=ctx.actor_admin_id,
        commit=False,
    )
    preview = ", ".join(u.email for u in users[:5])
    if len(users) > 5:
        preview += f" … +{len(users) - 5}"
    return _ok(
        "notify_users_by_role",
        role=role,
        count=sent,
        emails=[u.email for u in users],
        action_executed=True,
        task_answer=(
            f"C'est envoyé — {sent} notification(s) in-app diffusée(s) aux comptes « {role} » "
            f"({preview})."
        ),
    )


def _handle_notify_all_users(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title") or "Message Globex").strip()[:200]
    message = str(args.get("message") or "").strip()
    if not message:
        return _err("notify_all_users", "Message requis.")
    limit = _clamp_limit(args.get("limit"))
    users = list(ctx.db.scalars(_active_users_query(ctx.db, limit=limit)).all())
    if not users:
        return _err("notify_all_users", "Aucun utilisateur actif à notifier.")

    sent = 0
    for user in users:
        create_user_notification(
            ctx.db,
            user_id=user.id,
            type=str(args.get("type") or "system_alert"),
            title=title,
            message=message[:2000],
            sender_id=ctx.actor_admin_id,
            sender_role="admin",
            priority=str(args.get("priority") or "medium"),
            link=str(args.get("link") or "/notifications"),
        )
        sent += 1
    ctx.db.flush()
    write_log(
        ctx.db,
        action="admin.notify_all_users",
        message=f"Notification globale — {sent} destinataire(s)",
        category="admin",
        level="INFO",
        actor_user_id=ctx.actor_admin_id,
        commit=False,
    )
    preview = ", ".join(u.email for u in users[:5])
    if len(users) > 5:
        preview += f" … +{len(users) - 5}"
    return _ok(
        "notify_all_users",
        count=sent,
        emails=[u.email for u in users],
        action_executed=True,
        task_answer=(
            f"C'est envoyé — {sent} notification(s) diffusée(s) à tous les utilisateurs actifs "
            f"({preview})."
        ),
    )


def _handle_send_bulk_email(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    subject = str(args.get("subject") or "Message Globex FedEx").strip()[:200]
    body = str(args.get("body") or args.get("message") or "").strip()
    if not body:
        return _err("send_bulk_email", "Corps du message requis.")
    if not is_email_configured():
        return _err("send_bulk_email", "SMTP non configuré sur le serveur FedEx.")

    role = str(args.get("role") or "").strip() or None
    raw_ids = args.get("user_ids")
    user_ids: list[int] | None = None
    if isinstance(raw_ids, list) and raw_ids:
        user_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    limit = _clamp_limit(args.get("limit"))
    users = list(
        ctx.db.scalars(_active_users_query(ctx.db, role=role, user_ids=user_ids, limit=limit)).all(),
    )
    if not users:
        return _err("send_bulk_email", "Aucun destinataire trouvé.")

    sent = 0
    failed: list[str] = []
    for user in users:
        if not user.email:
            continue
        ok = send_email(to=user.email, subject=subject, body_text=body)
        if ok:
            sent += 1
        else:
            failed.append(user.email)

    write_log(
        ctx.db,
        action="admin.send_bulk_email",
        message=f"E-mails bulk — {sent}/{len(users)} envoyés",
        category="admin",
        level="INFO",
        actor_user_id=ctx.actor_admin_id,
        commit=False,
    )
    ctx.db.flush()
    if sent == 0:
        return _err("send_bulk_email", "Échec envoi SMTP pour tous les destinataires.")
    task = (
        f"C'est fait — {sent} e-mail(s) envoyé(s) sur {len(users)} destinataire(s)."
        + (f" Échecs : {', '.join(failed[:3])}" if failed else "")
    )
    return _ok(
        "send_bulk_email",
        sent=sent,
        total=len(users),
        failed=failed,
        action_executed=True,
        task_answer=task,
    )


def _resolve_bulk_user_ids(ctx: ToolExecutionContext, args: dict[str, Any]) -> list[int]:
    raw_ids = args.get("user_ids")
    if isinstance(raw_ids, list) and raw_ids:
        return [int(x) for x in raw_ids if str(x).isdigit()]

    dormant_days = args.get("dormant_days")
    if dormant_days is not None:
        rows = scan_dormant_accounts(
            ctx.db,
            days=int(dormant_days or 30),
            limit=_clamp_limit(args.get("limit")),
            role=str(args.get("role") or "").strip() or None,
        )
        return [int(r["user_id"]) for r in rows]

    return []


def _handle_suspend_users_bulk(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    user_ids = _resolve_bulk_user_ids(ctx, args)
    if not user_ids:
        return _err(
            "suspend_users_bulk",
            "Aucun compte ciblé — fournissez user_ids ou dormant_days.",
        )
    reason = str(args.get("reason") or "Suspension en lot — admin Globex OS")[:500]
    admin_id = ctx.actor_admin_id or ctx.user_id

    results: list[dict[str, Any]] = []
    ok_count = 0
    for uid in user_ids:
        user = ctx.db.get(User, uid)
        if user is None:
            results.append({"user_id": uid, "verified": False, "error": "introuvable"})
            continue
        if user.role == UserRole.admin.value:
            results.append({"user_id": uid, "email": user.email, "verified": False, "skip": "admin"})
            continue
        before = user.status
        ok = suspend_user(ctx.db, user.id, reason=reason, actor_admin_id=admin_id)
        ctx.db.refresh(user)
        verified = ok and user.status == UserStatus.suspended.value
        if verified:
            ok_count += 1
        results.append(
            {
                "user_id": user.id,
                "email": user.email,
                "status_before": before,
                "status_after": user.status,
                "verified": verified,
            },
        )

    write_log(
        ctx.db,
        action="admin.suspend_users_bulk",
        message=f"Suspension bulk — {ok_count}/{len(user_ids)}",
        category="admin",
        level="WARNING",
        actor_user_id=admin_id,
        commit=False,
    )
    ctx.db.flush()
    if ok_count == 0:
        return _err("suspend_users_bulk", "Aucun compte n'a pu être suspendu.")
    preview = ", ".join(r["email"] for r in results if r.get("verified"))[:200]
    return _ok(
        "suspend_users_bulk",
        success_count=ok_count,
        total=len(user_ids),
        results=results,
        action_executed=True,
        task_answer=(
            f"C'est fait — {ok_count} compte(s) suspendu(s)."
            + (f" Exemples : {preview}" if preview else "")
        ),
    )


BULK_HANDLERS: dict[str, Any] = {
    "scan_dormant_accounts": _handle_scan_dormant_accounts,
    "notify_users_by_role": _handle_notify_users_by_role,
    "notify_all_users": _handle_notify_all_users,
    "send_bulk_email": _handle_send_bulk_email,
    "suspend_users_bulk": _handle_suspend_users_bulk,
}
