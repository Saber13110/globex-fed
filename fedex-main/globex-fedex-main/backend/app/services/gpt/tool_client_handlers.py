"""Outils GPT portail client — surveillance, tickets, exports."""

from __future__ import annotations

from typing import Any

from app.models.user import User
from app.services.chat_export_service import latest_tracking_rows, session_tracking_numbers, user_recent_tracking_numbers
# from app.services.client_agent_service import open_client_support_ticket  # Phase 0 legacy désactivé
from app.services.gpt.tool_handlers import _err, _ok
from app.services.gpt.tool_types import ToolExecutionContext, ToolResult
from app.services.shipment_watch_service import ALERT_ALL, activate_client_shipment_watch


def _user(ctx: ToolExecutionContext) -> User | None:
    return ctx.db.get(User, ctx.user_id)


def _resolve_tracking_numbers(
    ctx: ToolExecutionContext,
    args: dict[str, Any],
    *,
    scope: str,
    limit: int = 20,
) -> list[str]:
    explicit = (args.get("tracking_number") or "").strip()
    if explicit:
        return [explicit]
    multi = args.get("tracking_numbers")
    if isinstance(multi, list):
        cleaned = [str(t).strip() for t in multi if str(t).strip()]
        if cleaned:
            return cleaned[:limit]
    session_id = ctx.session_id
    if scope == "session" and session_id:
        tns = session_tracking_numbers(ctx.db, session_id, ctx.user_id)
        return tns[:limit] if tns else []
    return user_recent_tracking_numbers(ctx.db, ctx.user_id, limit)[:limit]


def _handle_client_watch_shipment(ctx: ToolExecutionContext, args: dict[str, Any]):
    user = _user(ctx)
    if user is None:
        return _err("client_watch_shipment", "Utilisateur introuvable.")
    tn = (args.get("tracking_number") or "").strip()
    if not tn:
        return _err("client_watch_shipment", "Numéro de suivi requis.")
    try:
        outcome = activate_client_shipment_watch(
            ctx.db,
            user=user,
            tracking_number=tn,
            alert_type=str(args.get("alert_type") or ALERT_ALL),
            notify_email=bool(args.get("notify_email", True)),
            notify_in_app=bool(args.get("notify_in_app", True)),
        )
    except Exception as exc:
        return _err("client_watch_shipment", str(exc)[:200])
    return _ok(
        "client_watch_shipment",
        action_executed=True,
        tracking_number=tn,
        confirmation_sent=outcome.get("confirmation_sent"),
        alert_sent=outcome.get("alert_sent"),
        status=outcome.get("status"),
        location=outcome.get("location"),
    )


def _handle_client_open_support_ticket(ctx: ToolExecutionContext, args: dict[str, Any]):
    _ = ctx, args
    return _err("client_open_support_ticket", "Assistant en reconstruction.")


def _handle_client_export_tracking_excel(ctx: ToolExecutionContext, args: dict[str, Any]):
    scope = str(args.get("scope") or "recent").strip().lower()
    limit = max(1, min(int(args.get("limit") or 20), 50))
    tns = _resolve_tracking_numbers(ctx, args, scope=scope, limit=limit)
    session_id = ctx.session_id if scope == "session" else None
    rows = latest_tracking_rows(
        ctx.db,
        user_id=ctx.user_id,
        tracking_numbers=tns if tns else None,
        session_id=session_id,
        limit=max(len(tns), limit, 1),
    )
    if not rows:
        return _err(
            "client_export_tracking_excel",
            "Aucun colis à exporter. Suivez d'abord un numéro dans le chat.",
        )
    tns_final = [r.tracking_number for r in rows]
    export_download = {
        "session_id": ctx.session_id or 0,
        "tracking_numbers": tns_final,
        "preset": "tracking",
        "include_events": True,
        "format": "xlsx",
    }
    return _ok(
        "client_export_tracking_excel",
        action_executed=True,
        export_download=export_download,
        parcel_count=len(rows),
        tracking_numbers=tns_final,
    )


def _handle_client_export_tracking_pdf(ctx: ToolExecutionContext, args: dict[str, Any]):
    scope = str(args.get("scope") or "recent").strip().lower()
    preset = str(args.get("preset") or "tracking_summary").strip().lower()
    if preset not in {"tracking", "tracking_summary"}:
        preset = "tracking_summary"
    limit = max(1, min(int(args.get("limit") or 50), 100))
    tns = _resolve_tracking_numbers(ctx, args, scope=scope, limit=limit)
    session_id = ctx.session_id if scope == "session" else None
    rows = latest_tracking_rows(
        ctx.db,
        user_id=ctx.user_id,
        tracking_numbers=tns if tns else None,
        session_id=session_id,
        limit=limit,
    )
    if preset == "tracking_summary":
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date()
        rows = [r for r in rows if r.created_at and r.created_at.date() == today]
    if not rows and tns:
        rows = latest_tracking_rows(
            ctx.db,
            user_id=ctx.user_id,
            tracking_numbers=tns,
            session_id=session_id,
            limit=limit,
        )
    if not rows:
        session_tns: list[str] = []
        if ctx.session_id:
            session_tns = session_tracking_numbers(ctx.db, ctx.session_id, ctx.user_id)
        return ToolResult(
            name="client_export_tracking_pdf",
            success=False,
            error="Aucun colis enregistré pour cet export PDF.",
            data={
                "error_code": "no_parcels",
                "hint": "track_first_or_provide_number",
                "session_trackings": session_tns,
                "requested_trackings": tns,
            },
        )
    tns_final = [r.tracking_number for r in rows]
    export_download = {
        "session_id": ctx.session_id or 0,
        "tracking_numbers": tns_final,
        "preset": preset,
        "include_events": True,
        "format": "pdf",
    }
    return _ok(
        "client_export_tracking_pdf",
        action_executed=True,
        export_download=export_download,
        parcel_count=len(rows),
        preset=preset,
    )


def _handle_client_generate_text_pdf(ctx: ToolExecutionContext, args: dict[str, Any]):
    from app.services.ai_assistant.export_dataset_cache import store_client_pdf_blob
    from app.services.copilot_export_service import build_export_download_spec
    from app.services.simple_text_pdf_service import generate_text_pdf

    text = str(args.get("text") or "").strip()
    title = str(args.get("title") or text[:80] or "Document").strip()
    if not text:
        return _err("client_generate_text_pdf", "Texte requis pour générer le PDF.")

    try:
        pdf_bytes, filename = generate_text_pdf(text, title=title or None)
    except ValueError as exc:
        return _err("client_generate_text_pdf", str(exc))

    token = store_client_pdf_blob(
        user_id=ctx.user_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        meta={"text_preview": text[:200]},
    )
    export_download = build_export_download_spec(
        preset="text_pdf",
        filename=filename,
        fmt="pdf",
        export_token=token,
        session_id=ctx.session_id or 0,
    )
    return _ok(
        "client_generate_text_pdf",
        action_executed=True,
        text_preview=text[:200],
        filename=filename,
        pdf_size_bytes=len(pdf_bytes),
        export_download=export_download,
    )


CLIENT_HANDLERS = {
    "client_watch_shipment": _handle_client_watch_shipment,
    "client_open_support_ticket": _handle_client_open_support_ticket,
    "client_export_tracking_excel": _handle_client_export_tracking_excel,
    "client_export_tracking_pdf": _handle_client_export_tracking_pdf,
    "client_generate_text_pdf": _handle_client_generate_text_pdf,
}
