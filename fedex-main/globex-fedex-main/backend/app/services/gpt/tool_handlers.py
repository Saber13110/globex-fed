"""Handlers métier des outils GPT — réutilise les services existants."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole, UserStatus
from app.schemas.location import LocationAddressQuery, LocationSearchRequest
from app.services import fedex_service
from app.services.admin_logs_export_service import (
    build_logs_export_download,
    fetch_activity_logs,
    generate_activity_logs_pdf,
)
from app.services.command_center_service import build_command_center
from app.services.fedex_location_service import LocationSearchError, search_locations
from app.services.fedex_sandbox_whitelist import CLIENT_TRACKING_NOT_FOUND_HINT, FedExSandboxWhitelistError
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext, ToolResult


def _ok(name: str, **data: Any) -> ToolResult:
    return ToolResult(name=name, success=True, data=data)


def _err(name: str, message: str) -> ToolResult:
    return ToolResult(name=name, success=False, error=message)


def _handle_get_platform_stats(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    stats = build_command_center(ctx.db)
    return _ok(
        "get_platform_stats",
        active_users=stats.hero_stats[2].value,
        shipments_today=stats.hero_stats[0].value,
        open_incidents=stats.open_incidents,
        fedex_requests_today=stats.fedex_metrics.requests_today,
    )


def _handle_analyze_tracking(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    limit = min(int(args.get("limit") or 30), 100)
    rows = list(
        ctx.db.scalars(
            select(TrackingRequest)
            .options(joinedload(TrackingRequest.user))
            .order_by(TrackingRequest.created_at.desc())
            .limit(limit)
        ).all()
    )
    delayed = [r for r in rows if r.status and "delay" in (r.status or "").lower()]
    sample = []
    for r in rows[:15]:
        user = r.user
        sample.append(
            {
                "tracking_number": r.tracking_number,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user_id": r.user_id,
                "user_email": user.email if user else None,
                "user_name": (user.full_name if user else None),
                "user_role": user.role if user else None,
            }
        )
    return _ok(
        "analyze_tracking",
        total=len(rows),
        delayed_count=len(delayed),
        sample=sample,
    )


def _handle_analyze_tickets(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    import logging
    _log = logging.getLogger(__name__)
    try:
        limit = min(int(args.get("limit") or 20), 50)
        status_filter = (args.get("status") or "open").lower()
        stmt = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(limit)
        status_map = {
            "open": SupportTicketStatus.open,
            "pending": SupportTicketStatus.pending,
            "resolved": SupportTicketStatus.resolved,
            "closed": SupportTicketStatus.closed,
        }
        if status_filter in status_map:
            stmt = stmt.where(SupportTicket.status == status_map[status_filter])
        rows = list(ctx.db.scalars(stmt).all())
        sample = [
            {
                "id": t.id,
                "subject": (t.subject or "")[:120],
                "status": t.status.value if hasattr(t.status, "value") else t.status,
                "priority": t.priority.value if hasattr(getattr(t, "priority", None), "value") else getattr(t, "priority", None),
            }
            for t in rows[:10]
        ]
        _log.info("[analyze_tickets] status=%s count=%s", status_filter, len(rows))
        return _ok("analyze_tickets", count=len(rows), tickets=sample)
    except Exception as exc:
        _log.exception("[analyze_tickets] error: %s", exc)
        return _err("analyze_tickets", f"Impossible de lire les tickets ({str(exc)[:120]})")


def _handle_analyze_users(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    limit = min(max(int(args.get("limit") or 50), 1), 200)
    role_filter = (args.get("role") or args.get("role_filter") or "").strip().lower()
    status_filter = (args.get("status") or args.get("status_filter") or "").strip().lower()
    list_mode = str(args.get("list") or args.get("list_users") or "").lower() in {
        "1",
        "true",
        "yes",
        "all",
    }

    stmt = select(User).order_by(User.created_at.desc())
    if role_filter in {UserRole.client.value, UserRole.employe.value, UserRole.admin.value}:
        stmt = stmt.where(User.role == role_filter)
    elif role_filter in {"employee", "employees", "employe", "employés", "employes"}:
        stmt = stmt.where(User.role == UserRole.employe.value)
    elif role_filter in {"admin", "admins", "administrateur", "administrateurs"}:
        stmt = stmt.where(User.role == UserRole.admin.value)
    elif role_filter in {"client", "clients"}:
        stmt = stmt.where(User.role == UserRole.client.value)

    if status_filter in {UserStatus.active.value, UserStatus.suspended.value, UserStatus.pending.value, UserStatus.invited.value}:
        stmt = stmt.where(User.status == status_filter)
    elif status_filter in {"actif", "actifs", "active"}:
        stmt = stmt.where(User.status == UserStatus.active.value)
    elif status_filter in {"suspendu", "suspendus", "suspended"}:
        stmt = stmt.where(User.status == UserStatus.suspended.value)

    total = ctx.db.scalar(select(func.count()).select_from(User)) or 0
    active = ctx.db.scalar(
        select(func.count()).select_from(User).where(User.status == UserStatus.active.value)
    ) or 0
    suspended = ctx.db.scalar(
        select(func.count()).select_from(User).where(User.status == UserStatus.suspended.value)
    ) or 0
    admins = ctx.db.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.admin.value)
    ) or 0

    rows = list(ctx.db.scalars(stmt.limit(limit)).all())
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
    admin_accounts = [u for u in users if u["role"] == UserRole.admin.value]
    if not admin_accounts and role_filter in {"", "admin", "admins", "administrateur", "administrateurs"}:
        admin_accounts = [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name or "",
                "role": u.role,
                "status": u.status,
            }
            for u in ctx.db.scalars(
                select(User)
                .where(User.role == UserRole.admin.value)
                .order_by(User.created_at.asc())
                .limit(20)
            ).all()
        ]

    return _ok(
        "analyze_users",
        total=total,
        active=active,
        suspended=suspended,
        admins=admins,
        admin_accounts=admin_accounts,
        users=users,
        users_returned=len(users),
        list_mode=list_mode or bool(users),
    )


def _handle_analyze_logs(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    hours = min(max(int(args.get("hours") or 24), 1), 168)
    limit = min(int(args.get("limit") or 50), 100)
    logs = fetch_activity_logs(ctx.db, hours=hours, limit=limit)
    sample = [
        {
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "level": row.level,
            "action": row.action,
            "message": (row.message or "")[:180],
        }
        for row in logs[:20]
    ]
    levels: dict[str, int] = {}
    for row in logs:
        levels[row.level] = levels.get(row.level, 0) + 1
    return _ok("analyze_logs", hours=hours, count=len(logs), levels=levels, sample=sample)


def _handle_analyze_notifications(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.notifications_service import list_notifications

    limit = min(max(int(args.get("limit") or 10), 1), 50)
    status = "unread" if args.get("unread_only") else "all"
    priority = str(args.get("priority") or "all")
    if priority == "all" and args.get("critical_only"):
        priority = "critical"

    result = list_notifications(
        ctx.db,
        tab="all",
        status=status,
        priority=priority,
        sort="newest",
        page=1,
        page_size=limit,
    )
    sample = [
        {
            "id": item.id,
            "title": item.title,
            "message": (item.message or "")[:200],
            "category": item.category,
            "priority": item.priority,
            "is_read": item.is_read,
            "created_at": item.created_at.isoformat() if item.created_at else "",
            "time_label": item.time_label,
        }
        for item in result.items
    ]
    return _ok(
        "analyze_notifications",
        count=len(sample),
        total=result.total,
        unread_count=result.unread_count,
        sample=sample,
    )


def _handle_analyze_conversations(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.admin_conversations_service import build_conversations_page

    limit = min(max(int(args.get("limit") or 30), 1), 100)
    search = str(args.get("search") or "").strip()
    user_id = args.get("user_id")
    page = build_conversations_page(ctx.db, tab="all", search=search)
    conversations = list(page.conversations)
    if user_id is not None:
        try:
            uid = int(user_id)
            conversations = [c for c in conversations if c.user_id == uid]
        except (TypeError, ValueError):
            pass
    sample = [
        {
            "session_id": c.session_id,
            "title": c.title,
            "preview": c.preview,
            "user_id": c.user_id,
            "user_name": c.user_name,
            "user_email": c.user_email,
            "category": c.category,
            "status": c.status,
            "priority": c.priority,
            "updated_label": c.updated_label,
            "is_unread": c.is_unread,
        }
        for c in conversations[:limit]
    ]
    total_platform = page.kpis[0].value if page.kpis else len(conversations)
    return _ok(
        "analyze_conversations",
        total=total_platform,
        returned=len(sample),
        sample=sample,
    )


def _handle_export_activity_logs_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    hours = min(max(int(args.get("hours") or 24), 1), 168)
    limit = min(max(int(args.get("limit") or 500), 1), 500)
    logs = fetch_activity_logs(ctx.db, hours=hours, limit=limit)
    pdf_bytes, filename = generate_activity_logs_pdf(logs, hours=hours)
    export_spec = build_logs_export_download(hours, fmt="pdf")
    return _ok(
        "export_activity_logs_pdf",
        hours=hours,
        entries=len(logs),
        filename=filename,
        pdf_size_bytes=len(pdf_bytes),
        export_download=export_spec,
        action_executed=True,
    )


def _handle_export_activity_logs_excel(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.admin_logs_export_service import generate_activity_logs_excel

    hours = min(max(int(args.get("hours") or 24), 1), 168)
    limit = min(max(int(args.get("limit") or 500), 1), 500)
    logs = fetch_activity_logs(ctx.db, hours=hours, limit=limit)
    excel_bytes, filename = generate_activity_logs_excel(logs, hours=hours)
    export_spec = build_logs_export_download(hours, fmt="xlsx")
    return _ok(
        "export_activity_logs_excel",
        hours=hours,
        entries=len(logs),
        filename=filename,
        excel_size_bytes=len(excel_bytes),
        export_download=export_spec,
        action_executed=True,
    )


def _handle_module_export_pdf(ctx: ToolExecutionContext, args: dict[str, Any], *, module: str) -> ToolResult:
    """Export PDF contextuel (users, tickets, notifications, etc.) via export_pipeline."""
    from app.models.user import User as UserModel
    from app.services.ai_assistant.export_normalize import ExportDataError
    from app.services.ai_assistant.export_pipeline import (
        build_export_response_spec,
        export_tool_name,
        prepare_export_dataset,
    )
    from app.services.gpt.copilot_context_resolver import _fetch_module_data
    from app.services.gpt.copilot_conversation_state import CopilotConversationState

    admin = ctx.db.get(UserModel, ctx.user_id)
    if admin is None:
        return _err(f"export_{module}_pdf", "Utilisateur admin introuvable.")

    limit = min(max(int(args.get("limit") or 10), 1), 100)
    mod = (str(args.get("module") or module).strip().lower() if module == "generic" else module)
    export_fmt = str(args.get("format") or args.get("fmt") or "pdf").lower()
    if export_fmt not in {"pdf", "xlsx"}:
        export_fmt = "pdf"
    if mod not in {
        "notifications", "tracking", "users", "tickets", "conversations", "logs", "generic",
    }:
        mod = "generic"

    state = CopilotConversationState()
    tool_used, _data, items = _fetch_module_data(
        ctx.db, admin, module=mod, limit=limit, state=state,
    )
    if not items:
        return _err(export_tool_name(mod), "Aucune donnée à exporter pour ce module.")

    generated_by = admin.full_name or admin.email or "Administrateur Globex"
    tool_name = export_tool_name(mod, export_fmt) if mod != "generic" else "export_generic_result_pdf"

    try:
        _normalized, records, filename, _pdf, export_token = prepare_export_dataset(
            items,
            module=mod,
            message="",
            admin_id=admin.id,
            contextual=False,
            state_limit=None,
            explicit_limit=limit,
            source="refetch",
            fmt=export_fmt,
            generated_by=str(generated_by),
        )
    except ExportDataError as exc:
        return _err(tool_name, str(exc))

    export_spec = build_export_response_spec(
        module=mod,
        filename=filename,
        records=records,
        export_token=export_token,
        fmt=export_fmt,
        limit=records,
    )
    if mod == "tracking":
        numbers = ",".join(
            str(x.get("tracking_number") or x.get("numero") or "").strip()
            for x in items
            if x.get("tracking_number") or x.get("numero")
        )[:500]
        if numbers:
            export_spec["tracking_numbers"] = numbers

    return _ok(
        tool_name,
        module=mod,
        records=records,
        filename=filename,
        export_format=export_fmt,
        export_download=export_spec,
        action_executed=True,
        source_tool=tool_used,
    )


def _export_notifications_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_module_export_pdf(ctx, args, module="notifications")


def _export_users_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_module_export_pdf(ctx, args, module="users")


def _export_tracking_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_module_export_pdf(ctx, args, module="tracking")


def _export_tickets_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_module_export_pdf(ctx, args, module="tickets")


def _export_conversations_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_module_export_pdf(ctx, args, module="conversations")


def _export_generic_result_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_module_export_pdf(ctx, args, module="generic")


def _handle_generate_text_pdf(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.models.user import User as UserModel
    from app.services.ai_assistant.export_dataset_cache import store_pdf_blob
    from app.services.copilot_export_service import build_export_download_spec
    from app.services.simple_text_pdf_service import generate_text_pdf

    text = str(args.get("text") or "").strip()
    title = str(args.get("title") or text[:80]).strip()
    if not text:
        return _err("generate_text_pdf", "Texte requis pour générer le PDF.")

    try:
        pdf_bytes, filename = generate_text_pdf(text, title=title or None)
    except ValueError as exc:
        return _err("generate_text_pdf", str(exc))

    token = store_pdf_blob(
        admin_id=ctx.user_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        module="text",
        meta={"text_preview": text[:200]},
    )
    export_spec = build_export_download_spec(
        preset="admin_generic",
        filename=filename,
        fmt="pdf",
        export_token=token,
        module="text",
        records=1,
    )
    return _ok(
        "generate_text_pdf",
        text_preview=text[:200],
        filename=filename,
        pdf_size_bytes=len(pdf_bytes),
        export_download=export_spec,
        action_executed=True,
    )


def _handle_get_tracking_by_number(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    tn = str(args.get("tracking_number") or "").strip().replace(" ", "")
    if not tn:
        return _err("get_tracking_by_number", "Numéro de suivi requis.")
    row = ctx.db.scalar(
        select(TrackingRequest)
        .options(joinedload(TrackingRequest.user))
        .where(TrackingRequest.tracking_number.ilike(f"%{tn[-12:]}%"))
        .order_by(TrackingRequest.created_at.desc())
    )
    fedex_status = None
    location = None
    events_count = 0
    is_delayed = False
    try:
        shipment = fedex_service.get_shipment(tn)
        fedex_status = shipment.get("status")
        location = shipment.get("current_location")
        events_count = len(shipment.get("events") or [])
        is_delayed = "delay" in (fedex_status or "").lower() or "exception" in (fedex_status or "").lower()
    except Exception:
        pass
    user = row.user if row else None
    status = fedex_status or (row.status if row else None) or "unknown"
    return _ok(
        "get_tracking_by_number",
        tracking_number=tn,
        status=status,
        fedex_status=fedex_status,
        current_location=location,
        created_at=row.created_at.isoformat() if row and row.created_at else None,
        updated_at=row.created_at.isoformat() if row and row.created_at else None,
        user_id=row.user_id if row else None,
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        events_count=events_count,
        is_delayed=is_delayed,
        in_database=row is not None,
    )


def _handle_get_admin_users(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _handle_analyze_users(ctx, {**args, "role": "admin", "limit": args.get("limit") or 30})


def _handle_analyze_suspicious_logs(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.ai_assistant.specialized_routes import _analyze_suspicious_logs_payload

    hours = min(max(int(args.get("hours") or 24), 1), 168)
    logs = fetch_activity_logs(ctx.db, hours=hours, limit=200)
    analysis = _analyze_suspicious_logs_payload(logs, hours=hours)
    return _ok("analyze_suspicious_logs", **analysis)


def _handle_fedex_track_package(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    tn = str(args.get("tracking_number") or "").strip()
    if not tn:
        return _err("fedex_track_package", "Numéro de suivi requis.")
    try:
        shipment = fedex_service.get_shipment(tn)
        events = shipment.get("events") or []
        recent_events = [
            {
                "at": ev.get("at"),
                "description": ev.get("description"),
                "location": ev.get("location"),
            }
            for ev in events[:3]
            if isinstance(ev, dict)
        ]
        return _ok(
            "fedex_track_package",
            found=True,
            tracking_number=shipment.get("tracking_number"),
            status=shipment.get("status"),
            current_location=shipment.get("current_location"),
            estimated_delivery=shipment.get("estimated_delivery"),
            events_count=len(events),
            recent_events=recent_events,
        )
    except FedExSandboxWhitelistError as exc:
        return _ok(
            "fedex_track_package",
            found=False,
            tracking_number=exc.tracking_number,
            status="not_found",
            message=CLIENT_TRACKING_NOT_FOUND_HINT,
            reason="sandbox_whitelist_denied",
        )
    except TrackingLookupError as exc:
        return _ok(
            "fedex_track_package",
            found=False,
            tracking_number=tn,
            status="not_found",
            message=str(exc),
            reason="fedex_not_found",
        )
    except Exception as exc:
        return _err("fedex_track_package", f"FedEx indisponible : {exc}")


def _handle_find_fedex_location(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("find_fedex_location", "Requête de recherche requise.")
    country = str(args.get("country_code") or "MA").strip().upper()[:2]
    try:
        req = LocationSearchRequest(
            address=LocationAddressQuery(
                street_lines=[query],
                city=query,
                country_code=country,
            ),
            max_results=5,
        )
        result = search_locations(req)
        items = [
            {
                "name": loc.display_name,
                "city": loc.city,
                "postal_code": loc.postal_code,
                "distance_miles": loc.distance_miles,
            }
            for loc in (result.locations or [])[:5]
        ]
        return _ok("find_fedex_location", query=query, count=len(items), locations=items)
    except LocationSearchError as exc:
        return _err("find_fedex_location", str(exc))


def _handle_suspend_user(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.gpt.tool_communication_handlers import _execute_suspend_reactivate

    if args.get("_skip_approval") or ctx.admin_direct_order or ctx.skip_approval:
        return _execute_suspend_reactivate(ctx, args, action="suspend_user")
    uid = args.get("user_id")
    email = args.get("email")
    target = f"ID {uid}" if uid else (str(email) if email else "cible à confirmer")
    return ToolResult(
        name="suspend_user",
        success=True,
        needs_approval=True,
        approval_hint=(
            f"Action sensible — approbation requise pour suspendre {target}. "
            "Validez dans le Workspace ou le chat."
        ),
        data={"parameters": args},
    )


def _handle_reactivate_user(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.gpt.tool_communication_handlers import _execute_suspend_reactivate

    if args.get("_skip_approval") or ctx.admin_direct_order or ctx.skip_approval:
        return _execute_suspend_reactivate(ctx, args, action="reactivate_user")
    uid = args.get("user_id")
    email = args.get("email")
    target = f"ID {uid}" if uid else (str(email) if email else "cible à confirmer")
    return ToolResult(
        name="reactivate_user",
        success=True,
        needs_approval=True,
        approval_hint=(
            f"Action sensible — approbation requise pour réactiver {target}. "
            "Validez dans le Workspace ou le chat."
        ),
        data={"parameters": args},
    )


def _approval_action(name: str, args: dict[str, Any], *, label: str) -> ToolResult:
    return ToolResult(
        name=name,
        success=True,
        needs_approval=True,
        approval_hint=f"Action sensible — approbation requise : {label}. Paramètres : {args}",
        data={"parameters": args, "tool": name},
    )


def _handle_search_knowledge(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.gpt.knowledge_service import retrieve_knowledge
    from app.services.gpt.orchestrator import load_gpt_by_slug

    query = str(args.get("query") or "").strip()
    if not query:
        return _err("search_knowledge", "Requête de recherche requise.")
    gpt = load_gpt_by_slug(ctx.db, ctx.gpt_slug)
    if gpt is None:
        return _err("search_knowledge", "GPT introuvable.")
    limit = min(int(args.get("limit") or 5), 10)
    hits = retrieve_knowledge(
        ctx.db, gpt=gpt, query=query, language=ctx.ui_language, top_k=limit, min_score=0.4,
    )
    passages = [
        {
            "title": h.title,
            "excerpt": (h.content or "")[:400],
            "source": h.source_ref,
            "score": round(h.score, 3),
        }
        for h in hits
    ]
    return _ok("search_knowledge", query=query, count=len(passages), passages=passages)


def _handle_list_knowledge_documents(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.gpt.knowledge_service import list_knowledge_inventory
    from app.services.gpt.orchestrator import load_gpt_by_slug

    gpt = load_gpt_by_slug(ctx.db, ctx.gpt_slug)
    if gpt is None:
        return _err("list_knowledge_documents", "GPT introuvable.")
    docs = list_knowledge_inventory(ctx.db, gpt=gpt)[: min(int(args.get("limit") or 25), 50)]
    return _ok("list_knowledge_documents", count=len(docs), documents=docs)


def _handle_analyze_reports(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    t_limit = min(int(args.get("tracking_limit") or 10), 30)
    tk_limit = min(int(args.get("ticket_limit") or 10), 30)
    platform = _handle_get_platform_stats(ctx, {})
    tracking = _handle_analyze_tracking(ctx, {"limit": t_limit})
    tickets = _handle_analyze_tickets(ctx, {"status": "open", "limit": tk_limit})
    logs = _handle_analyze_logs(ctx, {"hours": 24, "limit": 10})
    return _ok(
        "analyze_reports",
        platform=platform.data if platform.success else {},
        tracking=tracking.data if tracking.success else {},
        tickets=tickets.data if tickets.success else {},
        logs=logs.data if logs.success else {},
    )


def _handle_analyze_security(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    try:
        from app.services.security_ids_service import incident_to_read, list_incidents

        status = str(args.get("status") or "open").strip().lower()
        limit = min(int(args.get("limit") or 15), 50)
        rows, total, open_count = list_incidents(ctx.db, status=status, limit=limit)
        sample = [incident_to_read(ctx.db, row) for row in rows[:limit]]
        return _ok(
            "analyze_security",
            total=total,
            open_count=open_count,
            sample=sample,
        )
    except Exception as exc:
        err = str(exc).lower()
        if "does not exist" in err or "no such table" in err or "relation" in err:
            return _ok(
                "analyze_security",
                total=0,
                open_count=0,
                sample=[],
                message=(
                    "Aucun outil sécurité connecté actuellement. "
                    "La table ou le module Security IDS doit être vérifié."
                ),
            )
        return _err("analyze_security", f"Erreur sécurité IDS : {str(exc)[:200]}")


def _handle_create_ticket(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    subject = str(args.get("subject") or "").strip()
    if not subject:
        return _err("create_ticket", "Sujet requis.")
    return _approval_action("create_ticket", args, label=f"création ticket « {subject[:80]} »")


def _handle_reply_support_ticket(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.admin_agent_tools import post_admin_support_reply

    ticket_id = args.get("ticket_id")
    body = str(args.get("reply_body") or args.get("body") or args.get("message") or "").strip()
    if not ticket_id:
        return _err("reply_support_ticket", "ticket_id requis.")
    if not body:
        return _err("reply_support_ticket", "Corps de la réponse requis.")
    if not (args.get("_skip_approval") or ctx.admin_direct_order or ctx.skip_approval):
        return _approval_action(
            "reply_support_ticket",
            {**args, "reply_body": body},
            label=f"réponse ticket #{ticket_id}",
        )
    admin_id = ctx.actor_admin_id or ctx.user_id
    ok, verification = post_admin_support_reply(
        ctx.db,
        ticket_id=int(ticket_id),
        body=body,
        admin_id=admin_id,
    )
    if not ok:
        return _err("reply_support_ticket", str(verification.get("error") or "échec publication"))
    ctx.db.commit()
    return _ok(
        "reply_support_ticket",
        ticket_id=int(ticket_id),
        verification=verification,
        action_executed=True,
        task_answer=f"FAIT — Réponse publiée sur le ticket #{ticket_id}.",
    )


def _handle_send_notification(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    from app.services.gpt.tool_communication_handlers import _handle_notify_user

    title = str(args.get("title") or "").strip()
    message = str(args.get("message") or "").strip()
    if not title:
        return _err("send_notification", "Titre requis.")
    if not (args.get("_skip_approval") or ctx.admin_direct_order or ctx.skip_approval):
        return _approval_action("send_notification", args, label=f"notification « {title[:60]} »")
    return _handle_notify_user(ctx, {**args, "title": title, "message": message})


def _handle_run_security_scan(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    return _approval_action("run_security_scan", args, label="scan sécurité IDS")


def _handle_create_agent_mission(ctx: ToolExecutionContext, args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title") or "").strip()
    if not title:
        return _err("create_agent_mission", "Titre de mission requis.")
    return _approval_action("create_agent_mission", args, label=f"mission « {title[:60]} »")


HANDLERS: dict[str, Callable[[ToolExecutionContext, dict[str, Any]], ToolResult]] = {
    "get_platform_stats": _handle_get_platform_stats,
    "analyze_tracking": _handle_analyze_tracking,
    "analyze_tickets": _handle_analyze_tickets,
    "analyze_users": _handle_analyze_users,
    "analyze_logs": _handle_analyze_logs,
    "analyze_notifications": _handle_analyze_notifications,
    "analyze_conversations": _handle_analyze_conversations,
    "search_knowledge": _handle_search_knowledge,
    "list_knowledge_documents": _handle_list_knowledge_documents,
    "analyze_reports": _handle_analyze_reports,
    "analyze_security": _handle_analyze_security,
    "get_tracking_by_number": _handle_get_tracking_by_number,
    "get_admin_users": _handle_get_admin_users,
    "analyze_suspicious_logs": _handle_analyze_suspicious_logs,
    "export_activity_logs_pdf": _handle_export_activity_logs_pdf,
    "export_activity_logs_excel": _handle_export_activity_logs_excel,
    "export_notifications_pdf": _export_notifications_pdf,
    "export_users_pdf": _export_users_pdf,
    "export_tracking_pdf": _export_tracking_pdf,
    "export_tickets_pdf": _export_tickets_pdf,
    "export_conversations_pdf": _export_conversations_pdf,
    "export_generic_result_pdf": _export_generic_result_pdf,
    "generate_text_pdf": _handle_generate_text_pdf,
    "fedex_track_package": _handle_fedex_track_package,
    "find_fedex_location": _handle_find_fedex_location,
    "suspend_user": _handle_suspend_user,
    "reactivate_user": _handle_reactivate_user,
    "create_ticket": _handle_create_ticket,
    "send_notification": _handle_send_notification,
    "run_security_scan": _handle_run_security_scan,
    "create_agent_mission": _handle_create_agent_mission,
}

from app.services.gpt.tool_communication_handlers import COMMUNICATION_HANDLERS  # noqa: E402
from app.services.gpt.tool_ticket_handlers import TICKET_HANDLERS  # noqa: E402
from app.services.gpt.tool_bulk_handlers import BULK_HANDLERS  # noqa: E402
from app.services.gpt.tool_extended_handlers import EXTENDED_HANDLERS  # noqa: E402
from app.services.gpt.tool_client_handlers import CLIENT_HANDLERS  # noqa: E402

HANDLERS.update(COMMUNICATION_HANDLERS)
HANDLERS.update(TICKET_HANDLERS)
HANDLERS.update(BULK_HANDLERS)
HANDLERS.update(EXTENDED_HANDLERS)
HANDLERS.update(CLIENT_HANDLERS)
HANDLERS["reply_support_ticket"] = _handle_reply_support_ticket
