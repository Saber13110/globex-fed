"""Envoi mail HTML + PDF pour le rapport quotidien client."""

from __future__ import annotations

import html
import logging

from app.models.user import User
from app.services.client_phase8.daily_report_collector import DailyReportSnapshot
from app.services.email_service import is_email_configured, send_email_with_attachment

logger = logging.getLogger(__name__)


def _escape(text: str) -> str:
    return html.escape(str(text or ""))


def build_daily_report_html(snapshot: DailyReportSnapshot, *, narrative: str) -> str:
    lang = snapshot.lang
    k = snapshot.kpi_dict()
    date_str = snapshot.generated_at_local.strftime("%d/%m/%Y")

    if lang == "en":
        title = "Your daily activity report"
        kpi_header = "Key indicators"
        unread_header = "Unread notifications"
        important_header = "Important alerts"
        footer = "Full report attached as PDF."
        metrics = [
            ("Chat messages", k["messages"]),
            ("Tracked shipments", k["trackings"]),
            ("Exports", k["exports"]),
            ("Watches", k["watches"]),
            ("Unread notifications", k["unread_notifications"]),
        ]
    else:
        title = "Votre rapport d'activité quotidien"
        kpi_header = "Indicateurs clés"
        unread_header = "Notifications non lues"
        important_header = "Alertes importantes"
        footer = "Rapport complet en pièce jointe PDF."
        metrics = [
            ("Messages chat", k["messages"]),
            ("Colis suivis", k["trackings"]),
            ("Exports", k["exports"]),
            ("Surveillances", k["watches"]),
            ("Notifications non lues", k["unread_notifications"]),
        ]

    rows = "".join(
        f"<tr><td style='padding:6px;border:1px solid #ddd'>{_escape(l)}</td>"
        f"<td style='padding:6px;border:1px solid #ddd;text-align:center'>{v}</td></tr>"
        for l, v in metrics
    )

    important_rows = ""
    for n in snapshot.important_notifications[:8]:
        important_rows += (
            f"<tr><td style='padding:4px;border:1px solid #eee'>{_escape(n.title)}</td>"
            f"<td style='padding:4px;border:1px solid #eee'>{_escape(n.related_tracking_number or '-')}</td></tr>"
        )

    unread_rows = ""
    for n in snapshot.unread_notifications[:8]:
        unread_rows += (
            f"<tr><td style='padding:4px;border:1px solid #eee'>{_escape(n.title)}</td>"
            f"<td style='padding:4px;border:1px solid #eee'>{_escape((n.message or '')[:80])}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:640px">
<h2 style="color:#1a365d">{_escape(title)}</h2>
<p style="color:#666">{_escape(snapshot.user_name)} · {_escape(date_str)}</p>
<p>{_escape(narrative)}</p>
<h3>{_escape(kpi_header)}</h3>
<table style="border-collapse:collapse;width:100%">{rows}</table>
<h3>{_escape(important_header)}</h3>
<table style="border-collapse:collapse;width:100%">
<tr><th style="text-align:left;padding:4px">Titre</th><th style="text-align:left;padding:4px">Colis</th></tr>
{important_rows or f"<tr><td colspan='2'>—</td></tr>"}
</table>
<h3>{_escape(unread_header)}</h3>
<table style="border-collapse:collapse;width:100%">
<tr><th style="text-align:left;padding:4px">Titre</th><th style="text-align:left;padding:4px">Message</th></tr>
{unread_rows or f"<tr><td colspan='2'>—</td></tr>"}
</table>
<p style="margin-top:20px;color:#666;font-size:12px">{_escape(footer)}</p>
<p style="color:#888;font-size:11px">— Agent FedEx Globex</p>
</body></html>"""


def send_daily_report_email(
    user: User,
    snapshot: DailyReportSnapshot,
    *,
    narrative: str,
    pdf_bytes: bytes,
    filename: str,
) -> bool:
    to = (getattr(user, "email", None) or snapshot.user_email or "").strip()
    if not to or not is_email_configured() or not pdf_bytes:
        return False
    lang = snapshot.lang
    date_str = snapshot.generated_at_local.strftime("%d/%m/%Y")
    if lang == "en":
        subject = f"[Globex FedEx] Daily activity report — {date_str}"
        body_text = (
            f"Hello {user.full_name or ''},\n\n{narrative}\n\n"
            f"Unread notifications: {snapshot.kpi_unread_notifications}. "
            f"See the attached PDF for the full report.\n\n— FedEx Globex Agent"
        )
    else:
        subject = f"[Globex FedEx] Rapport d'activité — {date_str}"
        body_text = (
            f"Bonjour {user.full_name or ''},\n\n{narrative}\n\n"
            f"Notifications non lues : {snapshot.kpi_unread_notifications}. "
            f"Consultez le PDF joint pour le rapport complet.\n\n— Agent FedEx Globex"
        )
    body_html = build_daily_report_html(snapshot, narrative=narrative)
    try:
        sent = send_email_with_attachment(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
            attachment_mime="application/pdf",
        )
        if sent:
            logger.info("Rapport quotidien envoyé à %s (%s)", to, filename)
        return sent
    except Exception:
        logger.exception("Échec envoi rapport quotidien")
        return False
