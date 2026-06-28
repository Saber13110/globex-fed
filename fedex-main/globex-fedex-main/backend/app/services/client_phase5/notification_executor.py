"""Exécution notifications_query — list / summarize / export_pdf."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.schemas.user_notifications import UserNotificationRead
from app.services.client_phase3.capabilities import CAP_PDF, has_capability
from app.services.client_phase3.pdf_body_composer import short_pdf_chat_reply
from app.services.client_phase5.notification_filters import (
    CHAT_LIST_MAX,
    NotificationQueryParams,
    section_label,
)
from app.services.client_phase5.notification_pdf import build_notifications_pdf_artifact
from app.services.client_phase7.export_email_hook import finalize_export_delivery
from app.services.client_phase5.notification_service import fetch_notifications_for_query
from app.services.client_phase5.notification_summary_llm import generate_notifications_summary
from app.services.user_notification_service import mark_all_user_notifications_read


def execute_mark_all_read(db: Session, user_id: int, *, lang: str) -> str:
    count = mark_all_user_notifications_read(db, user_id)
    if lang == "en":
        if count == 0:
            return "All your notifications were already marked as read."
        return f"I marked {count} notification(s) as read."
    if count == 0:
        return "Toutes vos notifications étaient déjà marquées comme lues."
    return f"J'ai marqué {count} notification(s) comme lue(s)."


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def _relative_label(dt: datetime | None, lang: str) -> str:
    if dt is None:
        return ""
    ref = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ref
    mins = int(delta.total_seconds() // 60)
    if lang == "en":
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins} min ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return ref.strftime("%d/%m/%y %H:%M")
    if mins < 1:
        return "à l'instant"
    if mins < 60:
        return f"il y a {mins} min"
    hours = mins // 60
    if hours < 24:
        return f"il y a {hours} h"
    return ref.strftime("%d/%m/%y %H:%M")


def _empty_message(lang: str, filter_label: str) -> str:
    if lang == "en":
        return f"No notifications match your request ({filter_label})."
    return f"Aucune notification ne correspond à votre demande ({filter_label})."


def _pdf_disabled_message(lang: str) -> str:
    if lang == "en":
        return "PDF export is not enabled for your account."
    return "L'export PDF n'est pas activé pour votre compte."


def _format_list_item(item: UserNotificationRead, index: int, lang: str) -> str:
    rel = _relative_label(item.created_at, lang)
    if lang == "en":
        status = "unread" if not item.is_read else "read"
    else:
        status = "non lu" if not item.is_read else "lu"
    tn = item.related_tracking_number or ""
    tn_part = f" ({tn})" if tn else ""
    msg = (item.message or "").strip()
    if len(msg) > 120:
        msg = msg[:117] + "..."
    return f"{index}. [{status}] {item.title} · {rel}{tn_part}\n   {msg}"


def _format_list_reply(
    items: list[UserNotificationRead],
    *,
    unread_count: int,
    total: int,
    filter_label: str,
    lang: str,
    display_limit: int,
    assistant_intro: str = "",
) -> str:
    chat_limit = min(len(items), min(max(display_limit, 1), CHAT_LIST_MAX))
    if lang == "en":
        header = (
            f"You have {unread_count} unread notification(s) on your account (total {total}). "
            f"Filter: {filter_label}."
        )
        if chat_limit < total:
            header += f" Showing the {chat_limit} most recent."
    else:
        header = (
            f"Vous avez {unread_count} notification(s) non lue(s) sur {total} au total. "
            f"Filtre : {filter_label}."
        )
        if chat_limit < total:
            header += f" Affichage des {chat_limit} plus récentes."

    lines: list[str] = []
    if assistant_intro.strip():
        lines.append(assistant_intro.strip())
    lines.append(header)
    lines.append("")
    for i, item in enumerate(items[:chat_limit], start=1):
        lines.append(_format_list_item(item, i, lang))
    return "\n".join(lines)


def execute_notifications_query(
    db: Session,
    user: User,
    session: ChatSession,
    params: NotificationQueryParams,
    *,
    message: str = "",
    ui_language: str | None = None,
    assistant_intro: str = "",
) -> tuple[str, dict[str, Any] | None]:
    lang = _lang(ui_language, user)
    filter_label = section_label(params.section, lang)
    result = fetch_notifications_for_query(db, user.id, params)

    if not result.items:
        return _empty_message(lang, filter_label), None

    mode = params.mode
    if mode == "export_pdf" or params.attach_pdf:
        if not has_capability(CAP_PDF):
            return _pdf_disabled_message(lang), None
        export_download, pdf_bytes, filename = build_notifications_pdf_artifact(
            user.id,
            session.id,
            result.items,
            unread_count=result.unread_count,
            total=result.total,
            filter_label=filter_label,
            lang=lang,
        )
        doc_title = "Mes notifications" if lang != "en" else "My notifications"
        reply = short_pdf_chat_reply(lang, doc_title=doc_title)
        if assistant_intro.strip():
            reply = f"{assistant_intro.strip()}\n\n{reply}"
        reply, export_download = finalize_export_delivery(
            user,
            session.id,
            message,
            reply,
            export_download,
            pdf_bytes,
            filename,
            "pdf",
            doc_title,
            ui_language=ui_language,
        )
        return reply, export_download

    if mode == "summarize":
        summary = generate_notifications_summary(
            result.items,
            lang=lang,
            filter_label=filter_label,
        )
        parts: list[str] = []
        if assistant_intro.strip():
            parts.append(assistant_intro.strip())
        if lang == "en":
            parts.append(f"**Summary** ({filter_label})")
        else:
            parts.append(f"**Résumé** ({filter_label})")
        parts.append(summary.strip())
        return "\n\n".join(parts), None

    reply = _format_list_reply(
        result.items,
        unread_count=result.unread_count,
        total=result.total,
        filter_label=filter_label,
        lang=lang,
        display_limit=params.limit,
        assistant_intro=assistant_intro,
    )
    return reply, None
