"""Service envoi e-mail admin → utilisateur."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.services.activity_log_service import write_log
from app.services.admin_client.email.email_narrative import compose_user_email_body, default_subject
from app.services.admin_client.email.email_types import AdminEmailDraft, EmailPlan, EmailScenario, EmailToolError
from app.services.ai_assistant.export_dataset_cache import get_owner_export_dataset
from app.services.email_service import is_email_configured, send_email, send_email_with_attachment


def resolve_recipient_user(
    db: Session,
    *,
    user_id: int | None = None,
    email: str | None = None,
) -> User | None:
    if user_id:
        return db.get(User, int(user_id))
    addr = (email or "").strip().lower()
    if not addr:
        return None
    return db.scalar(select(User).where(User.email.ilike(addr)))


def build_email_facts(
    recipient: User,
    admin: User,
    plan: EmailPlan,
) -> dict[str, Any]:
    return {
        "user_id": recipient.id,
        "user_name": recipient.full_name or recipient.email.split("@")[0],
        "user_email": recipient.email,
        "user_role": recipient.role,
        "user_status": recipient.status,
        "admin_name": admin.full_name or admin.email,
        "admin_note": (plan.admin_note or "").strip(),
        "scenario": plan.scenario.value,
    }


def build_user_email_draft(
    db: Session,
    admin: User,
    plan: EmailPlan,
    *,
    lang: str = "fr",
) -> AdminEmailDraft:
    recipient = resolve_recipient_user(
        db,
        user_id=plan.user_id,
        email=plan.recipient_email,
    )
    if recipient is None:
        raise EmailToolError("user_not_found")
    if recipient.role == UserRole.admin.value:
        raise EmailToolError("cannot_email_admin")
    if not (recipient.email or "").strip():
        raise EmailToolError("recipient_no_email")

    facts = build_email_facts(recipient, admin, plan)
    body, _ = compose_user_email_body(facts, scenario=plan.scenario, lang=lang)
    subject = (plan.subject_hint or "").strip() or default_subject(scenario=plan.scenario, lang=lang)

    attachment_bytes = None
    attachment_filename = None
    attachment_mime = "application/pdf"
    if plan.attachment_export_token:
        attachment_bytes, attachment_filename, attachment_mime = _load_attachment(
            plan.attachment_export_token,
            owner_id=admin.id,
        )

    return AdminEmailDraft(
        to=recipient.email.strip(),
        subject=subject[:200],
        body_text=body,
        user_id=recipient.id,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename,
        attachment_mime=attachment_mime,
    )


def _load_attachment(
    export_token: str,
    *,
    owner_id: int,
) -> tuple[bytes | None, str | None, str]:
    cached = get_owner_export_dataset(export_token, owner_id=owner_id)
    if not cached:
        return None, None, "application/pdf"
    fmt = str(cached.get("format") or "pdf").lower()
    filename = str(cached.get("filename") or "piece-jointe.pdf")
    if fmt == "xlsx":
        raw = cached.get("xlsx_bytes")
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raw = cached.get("pdf_bytes")
        mime = "application/pdf"
    if isinstance(raw, (bytes, bytearray)) and raw:
        return bytes(raw), filename, mime
    return None, None, mime


def send_user_email(
    db: Session,
    admin: User,
    draft: AdminEmailDraft,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    if not is_email_configured():
        raise EmailToolError("smtp_not_configured")

    to = (draft.to or "").strip()
    if not to:
        raise EmailToolError("recipient_no_email")

    try:
        if draft.attachment_bytes and draft.attachment_filename:
            ok = send_email_with_attachment(
                to=to,
                subject=draft.subject,
                body_text=draft.body_text,
                attachment_bytes=draft.attachment_bytes,
                attachment_filename=draft.attachment_filename,
                attachment_mime=draft.attachment_mime,
            )
        else:
            ok = send_email(to=to, subject=draft.subject, body_text=draft.body_text)
    except Exception as exc:  # noqa: BLE001
        raise EmailToolError(f"email_send_failed:{exc}") from exc

    if not ok:
        raise EmailToolError("email_send_failed:smtp")

    write_log(
        db,
        action="admin.send_user_email",
        message=f"E-mail envoyé à {to} — {draft.subject[:80]}",
        category="admin",
        level="INFO",
        user_id=draft.user_id,
        actor_user_id=admin.id,
        ip_address=ip_address or None,
        metadata={
            "subject": draft.subject[:200],
            "has_attachment": bool(draft.attachment_bytes),
        },
        commit=True,
    )
    return {
        "email_sent": True,
        "to": to,
        "subject": draft.subject,
        "user_id": draft.user_id,
    }


def search_user_by_ref(db: Session, message: str) -> User | None:
    from app.services.admin_client.users.users_followup import extract_email_from_message, extract_user_ref

    email = extract_email_from_message(message)
    if email:
        return resolve_recipient_user(db, email=email)
    ref = extract_user_ref(message)
    if ref is not None:
        return resolve_recipient_user(db, user_id=ref)
    return None
