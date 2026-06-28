"""Hook post-génération — export par mail sans altérer export_download."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.client_phase7.capabilities import has_email_export_capability
from app.services.client_phase7.export_email_intent import wants_export_by_email
from app.services.client_phase7.export_email_service import (
    build_email_suffix,
    send_client_export_email,
)
from app.services.client_phase7.export_session_pointer import remember_session_export
from app.services.email_service import is_email_configured

logger = logging.getLogger(__name__)


def _lang(user: User, ui_language: str | None) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def extract_file_bytes_from_cache(cached: dict[str, Any], fmt: str) -> bytes | None:
    if fmt == "xlsx":
        raw = cached.get("xlsx_bytes")
    else:
        raw = cached.get("pdf_bytes")
    return raw if isinstance(raw, (bytes, bytearray)) and raw else None


def apply_export_email_delivery(
    user: User,
    *,
    session_id: int,
    message: str,
    file_bytes: bytes,
    filename: str,
    fmt: str,
    export_download_spec: dict[str, Any],
    doc_label: str,
    ui_language: str | None = None,
) -> tuple[str, bool]:
    """
    Retourne (reply_suffix, email_sent).
    export_download_spec n'est jamais modifié.
    """
    token = export_download_spec.get("export_token")
    remember_session_export(
        session_id,
        export_token=str(token) if token else None,
        fmt=fmt,
        filename=filename,
    )

    lang = _lang(user, ui_language)
    has_email = bool(((getattr(user, "email", None) or "")).strip())
    smtp_ok = is_email_configured()

    if not has_email_export_capability() or not wants_export_by_email(message):
        return "", False

    if not has_email:
        return build_email_suffix(user, sent=False, smtp_ok=smtp_ok, has_email=False, lang=lang), False

    if not smtp_ok:
        return build_email_suffix(user, sent=False, smtp_ok=False, has_email=True, lang=lang), False

    sent = send_client_export_email(
        user,
        file_bytes=file_bytes,
        filename=filename,
        fmt=fmt,
        doc_label=doc_label,
    )
    return build_email_suffix(user, sent=sent, smtp_ok=True, has_email=True, lang=lang), sent


def append_export_email_suffix(reply: str, suffix: str) -> str:
    if not suffix:
        return reply
    base = (reply or "").strip()
    if not base:
        return suffix.strip()
    return f"{base}{suffix}"


def finalize_export_delivery(
    user: User,
    session_id: int,
    message: str,
    reply: str,
    export_download_spec: dict[str, Any],
    file_bytes: bytes,
    filename: str,
    fmt: str,
    doc_label: str,
    ui_language: str | None = None,
) -> tuple[str, dict[str, Any]]:
    suffix, _ = apply_export_email_delivery(
        user,
        session_id=session_id,
        message=message,
        file_bytes=file_bytes,
        filename=filename,
        fmt=fmt,
        export_download_spec=export_download_spec,
        doc_label=doc_label,
        ui_language=ui_language,
    )
    return append_export_email_suffix(reply, suffix), export_download_spec


def email_tracking_pdf_export(
    db: Session,
    user: User,
    session_id: int,
    message: str,
    reply: str,
    export_download_spec: dict[str, Any],
    *,
    ui_language: str | None = None,
    doc_label: str = "Export suivi FedEx",
) -> str:
    """Envoie par mail un export tracking preset (sans export_token) — spec inchangée."""
    from app.services.ai_assistant.export_dataset_cache import store_client_pdf_blob
    from app.services.chat_export_service import generate_tracking_history_pdf_bytes

    try:
        pdf_bytes, filename = generate_tracking_history_pdf_bytes(
            db,
            user_id=user.id,
            session_id=int(export_download_spec.get("session_id") or session_id) or None,
            tracking_numbers=export_download_spec.get("tracking_numbers"),
            preset=export_download_spec.get("preset"),
            include_events=bool(export_download_spec.get("include_events", True)),
        )
    except Exception:
        logger.exception("Échec génération PDF tracking pour envoi mail")
        return reply

    token = store_client_pdf_blob(
        user_id=user.id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        module="tracking",
    )
    pointer_spec = {
        **export_download_spec,
        "export_token": token,
        "filename": filename,
        "format": "pdf",
    }
    suffix, _ = apply_export_email_delivery(
        user,
        session_id=session_id,
        message=message,
        file_bytes=pdf_bytes,
        filename=filename,
        fmt="pdf",
        export_download_spec=pointer_spec,
        doc_label=doc_label,
        ui_language=ui_language,
    )
    return append_export_email_suffix(reply, suffix)
