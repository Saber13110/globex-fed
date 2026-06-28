"""PDF multi-sections pour le rapport quotidien client."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from app.services.client_phase8.daily_report_collector import DailyReportSnapshot


def _safe(text: str | None, *, max_len: int = 400) -> str:
    if not text:
        return "-"
    s = str(text).replace("\n", " ").strip()[:max_len]
    return s.encode("latin-1", errors="replace").decode("latin-1")


_SECTION = {
    "fr": {
        "title": "Rapport d'activité quotidien — Globex FedEx",
        "exec": "1. Synthèse exécutive",
        "kpi": "2. Indicateurs clés",
        "charts": "3. Graphiques",
        "important": "4. Alertes importantes",
        "unread": "5. Non lus — action requise",
        "detail": "6. Détail activité",
        "shipments": "Colis consultés",
        "exports": "Exports",
        "sessions": "Sessions chat",
        "none": "Aucun élément pour cette section.",
        "metric": "Indicateur",
        "value": "Valeur",
    },
    "en": {
        "title": "Daily Activity Report — Globex FedEx",
        "exec": "1. Executive summary",
        "kpi": "2. Key indicators",
        "charts": "3. Charts",
        "important": "4. Important alerts",
        "unread": "5. Unread — action required",
        "detail": "6. Activity detail",
        "shipments": "Tracked shipments",
        "exports": "Exports",
        "sessions": "Chat sessions",
        "none": "No items for this section.",
        "metric": "Metric",
        "value": "Value",
    },
}


def _draw_table(pdf: FPDF, headers: list[str], rows: list[list[str]], col_widths: list[int]) -> None:
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, _safe(h), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for row in rows:
        for i, cell in enumerate(row):
            pdf.cell(col_widths[i], 6, _safe(cell, max_len=60), border=1)
        pdf.ln()


def generate_daily_report_pdf(
    snapshot: "DailyReportSnapshot",
    *,
    narrative: str,
    chart_pngs: dict[str, bytes],
) -> tuple[bytes, str]:
    lang = snapshot.lang if snapshot.lang in _SECTION else "fr"
    L = _SECTION[lang]
    date_str = snapshot.generated_at_local.strftime("%d/%m/%Y")
    period = (
        f"{snapshot.period_start_local.strftime('%H:%M')} — "
        f"{snapshot.period_end_local.strftime('%H:%M')} UTC"
    )

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe(L["title"]), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, _safe(f"{snapshot.user_name} · {date_str} · {period}"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe(L["exec"]), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _safe(narrative, max_len=2000))
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe(L["kpi"]), ln=True)
    kpi_rows = [
        ["Messages chat", str(snapshot.kpi_messages)],
        ["Colis suivis", str(snapshot.kpi_trackings)],
        ["Exports", str(snapshot.kpi_exports)],
        ["Surveillances", str(snapshot.kpi_watches)],
        ["Notifications non lues", str(snapshot.kpi_unread_notifications)],
        ["Sessions chat", str(snapshot.kpi_sessions_today)],
    ]
    if lang == "en":
        kpi_rows = [
            ["Chat messages", str(snapshot.kpi_messages)],
            ["Tracked shipments", str(snapshot.kpi_trackings)],
            ["Exports", str(snapshot.kpi_exports)],
            ["Watches", str(snapshot.kpi_watches)],
            ["Unread notifications", str(snapshot.kpi_unread_notifications)],
            ["Chat sessions", str(snapshot.kpi_sessions_today)],
        ]
    _draw_table(pdf, [L["metric"], L["value"]], kpi_rows, [120, 60])
    pdf.ln(4)

    if chart_pngs:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _safe(L["charts"]), ln=True)
        for key in ("hourly", "status", "notifications"):
            png = chart_pngs.get(key)
            if not png:
                continue
            if pdf.get_y() > 220:
                pdf.add_page()
            pdf.image(BytesIO(png), x=10, w=180)
            pdf.ln(4)
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe(L["important"]), ln=True)
    if snapshot.important_notifications:
        imp_rows = []
        for n in snapshot.important_notifications[:15]:
            ts = n.created_at.strftime("%H:%M") if n.created_at else ""
            imp_rows.append(
                [
                    (n.priority or "medium").upper(),
                    (n.title or "")[:40],
                    (n.related_tracking_number or "-")[:18],
                    ts,
                ]
            )
        hdr = ["Priorité", "Titre", "Colis", "Heure"] if lang == "fr" else ["Priority", "Title", "Shipment", "Time"]
        _draw_table(pdf, hdr, imp_rows, [25, 80, 45, 25])
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _safe(L["none"]))
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe(L["unread"]), ln=True)
    if snapshot.unread_notifications:
        unread_rows = []
        for n in snapshot.unread_notifications[:20]:
            ts = n.created_at.strftime("%d/%m %H:%M") if n.created_at else ""
            unread_rows.append([(n.title or "")[:45], (n.message or "")[:50], ts])
        hdr = ["Titre", "Message", "Date"] if lang == "fr" else ["Title", "Message", "Date"]
        _draw_table(pdf, hdr, unread_rows, [55, 85, 30])
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _safe(L["none"]))
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe(L["detail"]), ln=True)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _safe(L["shipments"]), ln=True)
    if snapshot.shipments_today:
        rows = [[s["tracking_number"], s["status"], s["time"]] for s in snapshot.shipments_today[:12]]
        _draw_table(
            pdf,
            ["N° suivi", "Statut", "Heure"] if lang == "fr" else ["Tracking", "Status", "Time"],
            rows,
            [55, 80, 25],
        )
    else:
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _safe(L["none"]))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _safe(L["exports"]), ln=True)
    if snapshot.exports_today:
        rows = [[e["action"], e["time"]] for e in snapshot.exports_today[:10]]
        _draw_table(pdf, ["Action", "Heure"] if lang == "fr" else ["Action", "Time"], rows, [120, 40])
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _safe(L["sessions"]), ln=True)
    if snapshot.sessions_today:
        rows = [[s["title"], s["updated"]] for s in snapshot.sessions_today[:10]]
        _draw_table(pdf, ["Titre", "Màj"] if lang == "fr" else ["Title", "Updated"], rows, [120, 40])

    filename = f"rapport-activite-{date_str.replace('/', '-')}.pdf"
    return pdf.output(), filename
