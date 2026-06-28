"""Génération du rapport plateforme IA — Executive Summary + KPI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF
from sqlalchemy.orm import Session


def _safe(text: str | None, *, max_len: int = 400) -> str:
    if not text:
        return "-"
    s = str(text).replace("\n", " ").strip()[:max_len]
    return s.encode("latin-1", errors="replace").decode("latin-1")


def generate_platform_report_pdf(
    db: Session,
    admin: Any,
    *,
    hours: int = 24,
) -> tuple[bytes, str]:
    """Rapport exécutif PDF — users, tracking, logs, sécurité, tickets, notifications."""
    from sqlalchemy import func, select

    from app.models.activity_log import ActivityLog
    from app.models.security_incident import SecurityIncident
    from app.models.support_ticket import SupportTicket
    from app.models.tracking_request import TrackingRequest
    from app.models.user import User, UserStatus
    from app.services.ai_assistant.composite_tools import run_composite_tool
    from app.services.gpt.tool_types import ToolExecutionContext

    ctx = ToolExecutionContext(
        db=db, user_id=admin.id, user_role="admin", gpt_slug="fedex-admin-ops",
        actor_admin_id=admin.id, ui_language="fr", analysis_mode=True,
    )
    health = run_composite_tool(ctx, "analyze_platform_health", {})

    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    users_active = db.scalar(
        select(func.count()).select_from(User).where(User.status == UserStatus.active.value)
    ) or 0
    tracking_total = db.scalar(select(func.count()).select_from(TrackingRequest)) or 0
    tickets_open = db.scalar(
        select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "open")
    ) or 0
    incidents_open = db.scalar(
        select(func.count()).select_from(SecurityIncident).where(SecurityIncident.status == "open")
    ) or 0
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    logs_today = db.scalar(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.created_at >= since)
    ) or 0

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Globex FedEx — Rapport Plateforme IA", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, _safe(f"Genere le {ts} — Periode : {hours}h"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    sections = [
        ("Executive Summary", [
            f"Utilisateurs actifs : {users_active} / {users_total}",
            f"Operations tracking : {tracking_total}",
            f"Tickets ouverts : {tickets_open}",
            f"Incidents securite ouverts : {incidents_open}",
            f"Logs aujourd'hui : {logs_today}",
        ]),
        ("KPI Plateforme", [
            str(health.get("summary", health.get("status", "Analyse effectuee"))),
            f"Score sante : {health.get('health_score', 'N/A')}",
        ]),
        ("Incidents & Alertes", [
            f"{incidents_open} incident(s) securite ouvert(s)",
            f"{tickets_open} ticket(s) support ouvert(s)",
        ]),
        ("Recommandations", [
            "Surveiller les incidents securite ouverts et les tickets prioritaires.",
            "Verifier les colis en retard via le module tracking.",
            "Consulter les logs des dernieres 24h pour toute anomalie.",
        ]),
    ]

    for title, lines in sections:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _safe(title), ln=True)
        pdf.set_font("Helvetica", "", 10)
        for line in lines:
            pdf.multi_cell(0, 6, _safe(f"  - {line}"))
        pdf.ln(3)

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 5, _safe("Rapport genere par Copilot Globex — AI Command Center"))

    filename = f"platform-report-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    out = pdf.output()
    if isinstance(out, bytearray):
        return bytes(out), filename
    if isinstance(out, bytes):
        return out, filename
    return out.encode("latin-1"), filename
