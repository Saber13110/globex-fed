"""Export PDF Security IDS admin."""

from __future__ import annotations

import re
from typing import Any

from app.services.admin_client.security.security_compose import compose_security_response
from app.services.admin_client.security.security_followup import (
    has_incidents_list_data,
    is_security_history_context,
)
from app.services.admin_client.security.security_patterns import (
    REPORT_RE,
    is_security_report_message,
    normalize_security_text,
)
from app.services.admin_client.security.security_types import SecurityPlan, SecurityProfile, SecurityTaskType
from app.services.client_phase3.pdf_body_composer import strip_markdown_for_pdf
from app.services.client_phase3.pdf_text import append_pdf_ready_note, build_text_pdf_download


def is_security_pdf_followup(message: str, *, history_text: str = "") -> bool:
    """PDF demandé dans un contexte incidents / rapport sécurité — pas logs kernel."""
    from app.services.client_phase3.pdf_postprocess import is_pdf_only_followup, wants_pdf_format

    text = (message or "").strip()
    if not text:
        return False
    hist = history_text or ""
    security_ctx = has_incidents_list_data(hist) or is_security_history_context(hist)
    wants_pdf = wants_pdf_format(text) or is_pdf_only_followup(text) or bool(
        re.search(r"\b(pdf|fichier|t[eé]l[eé]charg|export|forme|document)\b", text, re.I)
    )
    if not wants_pdf:
        return False
    if security_ctx:
        return True
    return is_security_report_message(text)


def infer_pdf_plan(message: str, *, history_text: str = "") -> SecurityPlan:
    """Déduit liste incidents vs rapport selon le message et l'historique."""
    norm = normalize_security_text(message)
    if REPORT_RE.search(norm) or re.search(r"\brapport\b", norm, re.I):
        return SecurityPlan(
            task_type=SecurityTaskType.security_report,
            profile=SecurityProfile.REPORT,
            want_pdf=True,
            raw_matches=["pdf_report"],
        )
    if re.search(r"\br[eé]sum[eé]|resume\b", norm, re.I):
        return SecurityPlan(
            task_type=SecurityTaskType.security_incident_summary,
            profile=SecurityProfile.SUMMARY,
            want_pdf=True,
            raw_matches=["pdf_summary"],
        )
    if has_incidents_list_data(history_text) or is_security_history_context(history_text):
        return SecurityPlan(
            task_type=SecurityTaskType.security_incident_list,
            profile=SecurityProfile.LIST,
            status_filter="active",
            want_pdf=True,
            raw_matches=["pdf_list"],
        )
    return SecurityPlan(
        task_type=SecurityTaskType.security_report,
        profile=SecurityProfile.REPORT,
        want_pdf=True,
        raw_matches=["pdf_report_default"],
    )


def build_security_pdf_export(
    admin_id: int,
    session_id: int,
    *,
    plan: SecurityPlan,
    processed: dict[str, Any],
    lang: str = "fr",
) -> tuple[str, dict[str, Any] | None]:
    reply_md = compose_security_response(processed, plan, lang=lang)
    if not reply_md or reply_md.startswith("**Erreur"):
        msg = (
            "Aucun contenu sécurité à exporter en PDF."
            if lang == "fr"
            else "No security content to export as PDF."
        )
        return msg, None

    pdf_body = strip_markdown_for_pdf(reply_md)
    if plan.task_type == SecurityTaskType.security_incident_detail:
        title = "Incident sécurité Globex"
        filename_hint = f"incident_{plan.incident_id or 'detail'}"
    elif plan.task_type == SecurityTaskType.security_incident_list:
        title = "Incidents sécurité Globex"
        suffix = f"_{plan.status_filter}" if plan.status_filter else ""
        filename_hint = f"incidents_securite{suffix}"
    elif plan.task_type == SecurityTaskType.security_incident_summary:
        title = "Résumé incidents sécurité"
        filename_hint = "resume_incidents_securite"
    else:
        title = "Rapport sécurité Globex"
        filename_hint = "rapport_securite"

    export_download = build_text_pdf_download(
        admin_id,
        pdf_body,
        title=title,
        session_id=session_id,
    )
    export_download["filename"] = f"{filename_hint}.pdf"
    note = (
        "Votre PDF sécurité est prêt — utilisez le lien de téléchargement ci-dessous."
        if lang == "fr"
        else "Your security PDF is ready — use the download link below."
    )
    return append_pdf_ready_note(note), export_download
