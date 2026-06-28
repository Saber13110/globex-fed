"""Export PDF historique d'un seul colis — jamais liste globale."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.export_dataset_cache import store_export_dataset
from app.services.ai_assistant.export_pipeline import build_export_response_spec
from app.services.ai_assistant.tool_executor import build_tool_context, safe_tool_call
from app.services.copilot_export_service import build_export_download_spec
from app.services import fedex_service

logger = logging.getLogger(__name__)

_TRACKING_HISTORY_EXPORT_RE = __import__("re").compile(
    r"\b(exporte.?le|exporte le|son historique|historique du colis|historique de ce colis|"
    r"exporte son historique|exporte l.historique)\b",
    __import__("re").I,
)


def is_tracking_history_export(message: str, *, last_tracking_number: str | None) -> bool:
    text = (message or "").strip()
    if not text or not last_tracking_number:
        return False
    if _TRACKING_HISTORY_EXPORT_RE.search(text):
        return True
    if __import__("re").search(r"\bexport\b", text, __import__("re").I) and __import__(
        "re"
    ).search(r"\b(historique|pdf)\b", text, __import__("re").I):
        from app.services.ai_assistant.entity_memory import is_contextual_reference
        return is_contextual_reference(text)
    return False


def _fetch_tracking_detail(db: Session, admin: User, tracking_number: str) -> dict[str, Any]:
    ctx = build_tool_context(db, admin, ui_language=admin.preferred_language or "fr")
    item = safe_tool_call(ctx, "get_tracking_by_number", {"tracking_number": tracking_number})
    return item.get("response") or {}


def _fetch_events(tracking_number: str) -> list[dict[str, Any]]:
    try:
        shipment = fedex_service.get_shipment(tracking_number)
        events = shipment.get("events") or []
        return [e if isinstance(e, dict) else {"description": str(e)} for e in events]
    except Exception as exc:
        logger.warning("[TrackingExport] FedEx events unavailable: %s", exc)
        return []


def generate_tracking_history_pdf(
    tracking_data: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    """PDF d'un seul colis avec historique complet."""
    from fpdf import FPDF
    from app.services.copilot_export_service import _pdf_safe

    tn = tracking_data.get("tracking_number") or "—"
    status = tracking_data.get("status") or tracking_data.get("fedex_status") or "—"
    location = tracking_data.get("current_location") or "—"
    user_name = tracking_data.get("user_name") or "—"
    user_email = tracking_data.get("user_email") or "—"
    updated = (tracking_data.get("updated_at") or tracking_data.get("created_at") or "—")[:19]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _pdf_safe(f"Historique colis {tn}"), ln=True)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    for line in [
        f"Statut actuel : {status}",
        f"Localisation : {location}",
        f"Utilisateur lié : {user_name} ({user_email})",
        f"Dernière mise à jour : {updated}",
        f"Événements : {len(events)}",
        f"Généré par : {generated_by}",
    ]:
        pdf.multi_cell(pdf.epw, 6, _pdf_safe(line))
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe("Historique complet"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    if events:
        for i, ev in enumerate(events[:50], start=1):
            desc = ev.get("description") or ev.get("status") or str(ev)
            when = ev.get("timestamp") or ev.get("date") or ""
            pdf.multi_cell(pdf.epw, 5, _pdf_safe(f"{i}. [{when}] {desc}"))
    else:
        pdf.multi_cell(pdf.epw, 6, _pdf_safe("Aucun événement FedEx disponible pour ce colis."))
    filename = f"tracking-history-{tn}-{ts}.pdf"
    return pdf.output(), filename


def try_export_tracking_history(
    db: Session,
    admin: User,
    message: str,
    *,
    tracking_number: str,
    copilot_state: dict[str, Any] | None = None,
    lang: str = "fr",
) -> dict[str, Any] | None:
    """Export PDF historique d'un seul colis mémorisé."""
    if not is_tracking_history_export(message, last_tracking_number=tracking_number):
        return None

    logger.info("[TrackingExport] single colis export tn=%s", tracking_number)
    tracking_data = _fetch_tracking_detail(db, admin, tracking_number)
    if tracking_data.get("status") == "error":
        err = tracking_data.get("error") or "Colis introuvable."
        return {
            "reply": f"Impossible d'exporter l'historique : {err}",
            "answer": f"Impossible d'exporter l'historique : {err}",
            "intent": "export_tracking_history",
            "language": lang,
            "mode": "deterministic",
            "tools_used": ["get_tracking_by_number"],
            "error": err,
            "copilot_state": copilot_state or {},
        }

    events = _fetch_events(tracking_number)
    pdf_bytes, filename = generate_tracking_history_pdf(
        tracking_data,
        events,
        generated_by=admin.full_name or admin.email or "Administrateur Globex",
    )

    single_item = [{
        "tracking_number": tracking_number,
        "status": tracking_data.get("status"),
        "user_name": tracking_data.get("user_name"),
        "user_email": tracking_data.get("user_email"),
        "current_location": tracking_data.get("current_location"),
        "updated_at": tracking_data.get("updated_at"),
        "events_count": len(events),
    }]
    export_token = store_export_dataset(
        admin_id=admin.id,
        module="tracking_history",
        items=single_item,
        limit=1,
        source=f"tracking_history:{tracking_number}",
        filename=filename,
        fmt="pdf",
        meta={"tracking_number": tracking_number, "events": len(events)},
    )
    export_spec = build_export_response_spec(
        module="tracking",
        filename=filename,
        records=1,
        export_token=export_token,
        fmt="pdf",
        limit=1,
    )

    reply = (
        f"PDF généré avec succès : historique du colis **{tracking_number}** "
        f"({len(events)} événement(s)).\nTéléchargez : **{filename}**"
        if lang == "fr"
        else f"PDF generated: tracking history for **{tracking_number}**.\nDownload: **{filename}**"
    )

    from app.services.ai_assistant.conversation_state import ConversationState

    conv = ConversationState.from_copilot_state(copilot_state)
    conv.last_tracking_number = tracking_number
    conv.last_tracking_result = tracking_data
    conv.last_exportable_dataset = {"type": "tracking_history", "data": single_item}

    state_out = conv.merge_into_copilot_state(dict(copilot_state or {}))

    return {
        "reply": reply,
        "answer": reply,
        "intent": "export_tracking_history",
        "language": lang,
        "mode": "deterministic",
        "llm_provider": "local",
        "tools_used": ["export_tracking_history_pdf", "get_tracking_by_number"],
        "action_executed": True,
        "export_download": export_spec,
        "download_url": export_spec.get("url") or export_spec.get("download_url"),
        "file_name": filename,
        "records": 1,
        "confidence": 0.98,
        "error": None,
        "copilot_state": state_out,
    }
