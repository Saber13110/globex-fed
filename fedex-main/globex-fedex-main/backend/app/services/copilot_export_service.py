"""Exports PDF contextuels — templates professionnels, données normalisées."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF

from app.services.ai_assistant.export_normalize import (
    ExportDataError,
    normalize_items_for_export,
    validate_export_dataset,
)

logger = logging.getLogger(__name__)


def _pdf_safe(text: str | None, *, max_len: int = 500) -> str:
    if not text:
        return "-"
    s = str(text).replace("\r", " ").replace("\n", " ").strip()[:max_len]
    for a, b in (("—", "-"), ("'", "'"), ("'", "'"), ("«", '"'), ("»", '"')):
        s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _draw_summary_block(pdf: FPDF, lines: list[str]) -> None:
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 60)
    for line in lines:
        pdf.multi_cell(pdf.epw, 5, _pdf_safe(line))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)


def _draw_table(
    pdf: FPDF,
    *,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float] | None = None,
) -> None:
    epw = pdf.epw
    n = len(headers)
    if col_widths is None:
        col_widths = [epw / n] * n

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 230, 230)
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 7, _pdf_safe(header), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    for row in rows[:100]:
        for i, val in enumerate(row[:n]):
            pdf.cell(col_widths[i], 6, _pdf_safe(val, max_len=80), border=1)
        pdf.ln()


def _professional_pdf(
    *,
    title: str,
    summary_lines: list[str],
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float] | None = None,
    generated_by: str = "Administrateur Globex",
) -> bytes:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf = FPDF(orientation="L" if len(headers) > 5 else "P")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _pdf_safe(title), ln=True)
    pdf.ln(2)
    _draw_summary_block(pdf, summary_lines + [f"Date génération : {ts}", f"Généré par : {generated_by}"])
    pdf.ln(2)
    if not rows:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(pdf.epw, 7, _pdf_safe("Aucune donnée à exporter."))
    else:
        _draw_table(pdf, headers=headers, rows=rows, col_widths=col_widths)
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(pdf.epw, 5, _pdf_safe("Export Globex AI Command Center — document confidentiel"))
    return pdf.output()


def generate_notifications_pdf(
    items: list[dict[str, Any]],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    normalized = validate_export_dataset(items, "notifications")
    unread = sum(1 for r in normalized if r.get("lu") == "Non lu")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    summary = [
        f"Nombre de notifications exportées : {len(normalized)}",
        f"Non lues : {unread}",
    ]
    rows = [
        [str(i), r["titre"], r["message"], r["type"], r["priorite"], r["date"], r["lu"]]
        for i, r in enumerate(normalized, start=1)
    ]
    body = _professional_pdf(
        title="Notifications Globex",
        summary_lines=summary,
        headers=["N°", "Titre", "Message", "Type", "Priorité", "Date", "Statut lu/non lu"],
        rows=rows,
        col_widths=[10, 35, 55, 25, 22, 28, 22],
        generated_by=generated_by,
    )
    return body, f"notifications-{len(normalized)}-items-{ts}.pdf"


def generate_users_pdf(
    items: list[dict[str, Any]],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    normalized = validate_export_dataset(items, "users")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    summary = [f"Nombre d'utilisateurs exportés : {len(normalized)}"]
    rows = [
        [str(i), r["nom"], r["email"], r["role"], r["statut"], r["id"]]
        for i, r in enumerate(normalized, start=1)
    ]
    body = _professional_pdf(
        title="Utilisateurs Globex",
        summary_lines=summary,
        headers=["N°", "Nom", "Email", "Rôle", "Statut", "ID"],
        rows=rows,
        col_widths=[10, 40, 55, 25, 25, 15],
        generated_by=generated_by,
    )
    return body, f"users-{len(normalized)}-items-{ts}.pdf"


def generate_tracking_pdf(
    items: list[dict[str, Any]],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    normalized = validate_export_dataset(items, "tracking")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    summary = [f"Nombre de colis exportés : {len(normalized)}"]
    rows = [
        [str(i), r["numero"], r["statut"], r["utilisateur"], r["email"], r["date"]]
        for i, r in enumerate(normalized, start=1)
    ]
    body = _professional_pdf(
        title="Opérations tracking Globex",
        summary_lines=summary,
        headers=["N°", "Numéro", "Statut", "Utilisateur", "Email", "Date"],
        rows=rows,
        generated_by=generated_by,
    )
    return body, f"tracking-{len(normalized)}-items-{ts}.pdf"


def generate_tickets_pdf(
    items: list[dict[str, Any]],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    normalized = validate_export_dataset(items, "tickets")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    summary = [f"Nombre de tickets exportés : {len(normalized)}"]
    rows = [
        [str(i), r["id"], r["sujet"], r["statut"], r["priorite"], r["utilisateur"]]
        for i, r in enumerate(normalized, start=1)
    ]
    body = _professional_pdf(
        title="Tickets support Globex",
        summary_lines=summary,
        headers=["N°", "ID", "Sujet", "Statut", "Priorité", "Utilisateur"],
        rows=rows,
        generated_by=generated_by,
    )
    return body, f"tickets-{len(normalized)}-items-{ts}.pdf"


def generate_conversations_pdf(
    items: list[dict[str, Any]],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    rows_raw = []
    for i, raw in enumerate(items[:100], start=1):
        if not isinstance(raw, dict):
            continue
        rows_raw.append([
            str(i),
            str(raw.get("title") or raw.get("titre") or "-"),
            str(raw.get("user_name") or raw.get("user_label") or "-"),
            str(raw.get("status") or raw.get("statut") or "-"),
            str(raw.get("preview") or raw.get("message") or "-")[:120],
        ])
    if not rows_raw:
        raise ExportDataError("Impossible de générer le PDF : les données reçues sont vides ou mal mappées.")
    body = _professional_pdf(
        title="Conversations Globex",
        summary_lines=[f"Nombre de conversations exportées : {len(rows_raw)}"],
        headers=["N°", "Titre", "Utilisateur", "Statut", "Aperçu"],
        rows=rows_raw,
        generated_by=generated_by,
    )
    return body, f"conversations-{len(rows_raw)}-items-{ts}.pdf"


def generate_generic_result_pdf(
    *,
    module: str,
    payload: dict[str, Any],
) -> tuple[bytes, str]:
    """PDF générique à partir du dernier payload outil."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    sample = payload.get("sample") or payload.get("tickets") or payload.get("documents") or payload.get("items") or []
    if isinstance(sample, list) and sample and isinstance(sample[0], dict):
        normalized = normalize_items_for_export(sample, module)
        if normalized:
            keys = list(normalized[0].keys())[:8]
            headers = ["N°"] + [k.replace("_", " ").title() for k in keys]
            rows = [[str(i)] + [str(r.get(k, "-")) for k in keys] for i, r in enumerate(normalized, start=1)]
            body = _professional_pdf(
                title=f"Export {module} — Globex",
                summary_lines=[f"Nombre d'éléments exportés : {len(rows)}"],
                headers=headers,
                rows=rows,
            )
            return body, f"{module}-{len(rows)}-items-{ts}.pdf"

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _pdf_safe(f"Export {module}"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:8000]
    for line in text.splitlines():
        pdf.multi_cell(0, 5, _pdf_safe(line, max_len=400))
    return pdf.output(), f"{module}-export-{ts}.pdf"


def generate_module_pdf(
    items: list[dict[str, Any]],
    *,
    module: str,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    """Point d'entrée unique — génère le PDF du module avec validation."""
    generators = {
        "notifications": generate_notifications_pdf,
        "users": generate_users_pdf,
        "tracking": generate_tracking_pdf,
        "tickets": generate_tickets_pdf,
        "conversations": generate_conversations_pdf,
    }
    gen = generators.get(module)
    if gen:
        logger.info("[EXPORT] pdf_generated=true module=%s count=%s", module, len(items))
        return gen(items, generated_by=generated_by)
    return generate_generic_result_pdf(module=module, payload={"sample": items, "items": items})


def build_context_export_pdf_from_items(
    items: list[dict[str, Any]],
    *,
    module: str,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    """Génère un PDF à partir d'un dataset exact (cache / mémoire session)."""
    return generate_module_pdf(items, module=module, generated_by=generated_by)


def build_context_export_pdf(
    db: Any,
    admin: Any,
    *,
    module: str,
    limit: int = 10,
    hours: int = 24,
) -> tuple[bytes, str]:
    """Re-fetch legacy — préférer build_context_export_pdf_from_items avec cache."""
    from app.services.gpt.copilot_context_resolver import _fetch_module_data
    from app.services.gpt.copilot_conversation_state import CopilotConversationState

    state = CopilotConversationState()
    _, data, items = _fetch_module_data(
        db, admin, module=module, limit=limit, state=state,
    )
    if module == "logs":
        from app.services.admin_logs_export_service import fetch_activity_logs, generate_activity_logs_pdf

        logs = fetch_activity_logs(db, hours=hours, limit=500)
        return generate_activity_logs_pdf(logs, hours=hours)
    name = getattr(admin, "full_name", None) or getattr(admin, "email", None) or "Administrateur Globex"
    return generate_module_pdf(items[:limit], module=module, generated_by=str(name))


def build_export_download_spec(
    *,
    preset: str,
    filename: str,
    fmt: str = "pdf",
    **extra: Any,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "preset": preset,
        "filename": filename,
        "format": fmt,
    }
    spec.update({k: v for k, v in extra.items() if v is not None})
    return spec
