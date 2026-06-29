"""PDF rapport dashboard retards."""

from __future__ import annotations

from app.models.user import User
from app.services.admin_client.dashboard.dashboard_compose import compose_dashboard_response
from app.services.admin_client.dashboard.dashboard_charts import render_dashboard_charts
from app.services.admin_client.dashboard.dashboard_types import DashboardPlan
from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot
from app.services.client_phase3.pdf_body_composer import short_pdf_chat_reply
from app.services.client_phase3.pdf_text import append_pdf_ready_note, build_text_pdf_download


def build_delay_report_pdf(
    admin: User,
    session,
    snapshot: DashboardSnapshot,
    plan: DashboardPlan,
) -> tuple[str, dict]:
    """Génère PDF texte + note de téléchargement."""
    lang = snapshot.lang
    body = compose_dashboard_response(snapshot, plan)
    charts = render_dashboard_charts(snapshot)
    if charts:
        body += "\n\n"
        body += (
            f"Graphiques générés : {', '.join(charts.keys())}."
            if lang == "fr"
            else f"Charts generated: {', '.join(charts.keys())}."
        )

    title = "Rapport retards Globex" if lang == "fr" else "Globex delay report"
    export_download = build_text_pdf_download(
        admin.id,
        body,
        title=title,
        session_id=session.id,
    )
    reply = append_pdf_ready_note(short_pdf_chat_reply(lang, doc_title=title))
    return reply, export_download
