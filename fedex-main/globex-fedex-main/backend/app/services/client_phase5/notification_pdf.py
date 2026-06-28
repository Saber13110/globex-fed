"""Export PDF notifications client."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.user_notifications import UserNotificationRead
from app.services.ai_assistant.export_dataset_cache import store_client_pdf_blob
from app.services.client_phase3.pdf_body_composer import strip_markdown_for_pdf
from app.services.copilot_export_service import build_export_download_spec
from app.services.simple_text_pdf_service import generate_text_pdf


def _format_item_line(item: UserNotificationRead, index: int, lang: str) -> str:
    created = item.created_at.strftime("%d/%m/%Y %H:%M") if item.created_at else ""
    if lang == "en":
        status = "UNREAD" if not item.is_read else "read"
    else:
        status = "NON LU" if not item.is_read else "lu"
    tn = item.related_tracking_number or ""
    tn_part = f" ({tn})" if tn else ""
    msg = (item.message or "").strip().replace("\n", " ")
    if len(msg) > 200:
        msg = msg[:197] + "..."
    return (
        f"{index}. [{status}] {item.title} · {created}{tn_part}\n"
        f"   {msg}"
    )


def build_notifications_pdf_body(
    items: list[UserNotificationRead],
    *,
    unread_count: int,
    total: int,
    filter_label: str,
    lang: str,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    if lang == "en":
        header = (
            f"MY NOTIFICATIONS — {ts}\n"
            f"Filter: {filter_label}\n"
            f"Unread: {unread_count} / Total account: {total}\n"
            f"Exported: {len(items)} notification(s)\n"
        )
    else:
        header = (
            f"MES NOTIFICATIONS — {ts}\n"
            f"Filtre : {filter_label}\n"
            f"Non lues : {unread_count} / Total compte : {total}\n"
            f"Exportées : {len(items)} notification(s)\n"
        )
    lines = [header, ""]
    for i, item in enumerate(items, start=1):
        lines.append(_format_item_line(item, i, lang))
        lines.append("")
    return "\n".join(lines).strip()


def build_notifications_pdf_artifact(
    user_id: int,
    session_id: int,
    items: list[UserNotificationRead],
    *,
    unread_count: int,
    total: int,
    filter_label: str,
    lang: str,
) -> tuple[dict[str, Any], bytes, str]:
    body = build_notifications_pdf_body(
        items,
        unread_count=unread_count,
        total=total,
        filter_label=filter_label,
        lang=lang,
    )
    cleaned = strip_markdown_for_pdf(body)
    title = "Mes notifications FedEx Globex" if lang != "en" else "My FedEx Globex notifications"
    pdf_bytes, filename = generate_text_pdf(cleaned, title=title)
    token = store_client_pdf_blob(
        user_id=user_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        module="notifications",
        meta={"count": len(items), "filter": filter_label},
    )
    spec = build_export_download_spec(
        preset="notifications_pdf",
        filename=filename,
        fmt="pdf",
        export_token=token,
        session_id=session_id,
    )
    return spec, pdf_bytes, filename


def build_notifications_pdf_download(
    user_id: int,
    session_id: int,
    items: list[UserNotificationRead],
    *,
    unread_count: int,
    total: int,
    filter_label: str,
    lang: str,
) -> dict[str, Any]:
    spec, _, _ = build_notifications_pdf_artifact(
        user_id,
        session_id,
        items,
        unread_count=unread_count,
        total=total,
        filter_label=filter_label,
        lang=lang,
    )
    return spec
