"""Priorité des intents admin — évite que document followup intercepte notif/suivi/export."""

from __future__ import annotations

import re

from app.services.admin_client.dashboard.dashboard_workspace import (
    is_dashboard_report_message,
    is_dashboard_workspace,
)
from app.services.admin_client.reports.reports_workspace import is_reports_workspace
from app.services.admin_client.users.users_workspace import is_dashboard_users_kpi, is_users_workspace
from app.services.admin_client.logs.logs_workspace import is_logs_workspace
from app.services.admin_client.logs.logs_patterns import is_user_scoped_logs_message
from app.services.admin_client.tickets.tickets_workspace import is_tickets_workspace
from app.services.admin_client.tickets.tickets_followup import (
    extract_ticket_ref,
    is_tickets_history_context,
    _message_targets_logs,
)
from app.services.admin_client.logs.logs_followup import is_logs_history_context
from app.services.admin_client.security.security_patterns import (
    REPORT_RE as SECURITY_REPORT_RE,
    is_logs_anomaly_scope,
    is_security_report_message,
    message_targets_incidents,
    normalize_security_text,
)
from app.services.admin_client.security.security_followup import (
    is_security_followup_message,
    is_security_history_context,
)
from app.services.admin_client.security.security_workspace import is_security_workspace
from app.services.admin_client.notifications_adapter import is_mark_read_intent
from app.services.admin_client.pdf_clarify_followup import is_pdf_clarify_choice_message
from app.services.client_phase3.excel_postprocess import wants_excel_format
from app.services.client_phase3.pdf_postprocess import wants_pdf_format
from app.services.client_phase5.notification_filters import is_notification_workspace
from app.services.client_phase9.document_session import is_document_followup_question
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

_EXPLICIT_EXPORT_RE = re.compile(
    r"\b("
    r"export|exporter|g[eé]n[eè]re|g[eé]nere|t[eé]l[eé]charger|telecharger|"
    r"en pdf|mets.*pdf|met.*pdf|fichier pdf"
    r")\b",
    re.I,
)


def is_admin_explicit_notification(message: str) -> bool:
    """Tour notifications admin (liste, résumé, marquer lues, export PDF notifs)."""
    text = (message or "").strip()
    if not text:
        return False
    return is_notification_workspace(text) or is_mark_read_intent(text)


def _wants_explicit_file_export(message: str) -> bool:
    """Export fichier explicite — pas une simple mention « document » dans une question."""
    text = (message or "").strip()
    if not text:
        return False
    if wants_excel_format(text):
        return True
    if "pdf" in text.lower():
        return True
    return bool(_EXPLICIT_EXPORT_RE.search(text))


def should_route_dashboard(message: str, *, history_text: str = "") -> bool:
    """Tour dashboard admin — workspace prime ; exclusions strictes suivi/PDF colis/notifs."""
    text = (message or "").strip()
    from app.services.admin_client.security.security_patterns import (
        REPORT_RE,
        SUMMARY_RE,
        normalize_security_text,
        message_targets_incidents,
    )
    from app.services.admin_client.security.security_followup import is_security_history_context

    norm = normalize_security_text(text)
    if message_targets_incidents(text) and (
        REPORT_RE.search(norm)
        or SUMMARY_RE.search(norm)
        or re.search(r"\b(scan|liste|detail|fiche|rapport).{0,25}incident", norm, re.I)
    ):
        return False
    if is_security_history_context(history_text) and message_targets_incidents(text):
        return False
    if not is_dashboard_workspace(text):
        return False

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False

    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request
    from app.services.chat_shipment_reply import is_session_follow_up

    if is_admin_shipment_pdf_request(text) and not is_dashboard_report_message(text):
        return False
    if wants_pdf_format(text) and re.search(
        r"\b(colis|suivi|tracking|shipment|package)\b", text, re.I
    ):
        return False
    if is_session_follow_up(text) and extract_tracking_number(history_text or ""):
        return False

    return True


def should_route_reports(message: str, *, history_text: str = "") -> bool:
    """Tour centre de rapports admin — après dashboard, avant PDF colis."""
    text = (message or "").strip()
    from app.services.admin_client.email.email_patterns import is_send_user_email_message
    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if is_send_user_email_message(text):
        return False

    if wants_pdf_format(text) and is_users_workspace(text, history_text=history_text):
        return False
    if SECURITY_REPORT_RE.search(text):
        return False
    if not is_reports_workspace(text, history_text=history_text):
        return False

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        from app.services.admin_client.reports.reports_followup import (
            extract_report_run_ref,
            is_reports_history_context,
        )

        if not (is_reports_history_context(history_text) and extract_report_run_ref(text)):
            return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False
    if is_dashboard_report_message(text):
        return False
    if should_route_dashboard(text, history_text=history_text):
        return False

    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request

    if re.search(r"\b(colis|suivi|tracking|shipment|package)\b", text, re.I):
        if re.search(
            r"\b(rapports?|reports?|exports?|tracking-history|delivery-performance|"
            r"financial-summary|exception-report|centre\s+de\s+rapports?)\b",
            text,
            re.I,
        ):
            return True
        if is_admin_shipment_pdf_request(text) or wants_pdf_format(text):
            return False
    return True


def should_route_security(message: str, *, history_text: str = "") -> bool:
    """Tour Security IDS admin — après reports, avant logs."""
    text = (message or "").strip()
    from app.services.admin_client.security.security_pdf import is_security_pdf_followup

    if is_security_pdf_followup(text, history_text=history_text):
        return True
    if is_security_report_message(text):
        return True
    if is_logs_anomaly_scope(text):
        return False
    if is_security_history_context(history_text) and message_targets_incidents(text):
        return True
    if is_security_followup_message(text, history_text=history_text):
        return True
    if not is_security_workspace(text, history_text=history_text):
        return False

    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if wants_pdf_format(text) and is_users_workspace(text, history_text=history_text):
        return False

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False
    if is_dashboard_report_message(text):
        return False
    if should_route_reports(text, history_text=history_text):
        return False

    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request

    if re.search(r"\b(colis|suivi|tracking|shipment|package)\b", text, re.I):
        if is_admin_shipment_pdf_request(text) or wants_pdf_format(text):
            return False
    return True


def should_route_logs(message: str, *, history_text: str = "") -> bool:
    """Tour journaux d'activité admin — après reports, avant tickets."""
    text = (message or "").strip()
    from app.services.admin_client.email.email_patterns import should_defer_logs_to_users

    if should_defer_logs_to_users(text):
        return False
    from app.services.admin_client.logs.logs_export import (
        is_logs_direct_export_message,
        is_logs_excel_followup,
        is_logs_pdf_followup,
    )

    if is_logs_direct_export_message(text):
        return True
    if is_logs_excel_followup(text, history_text=history_text):
        return True
    if is_logs_pdf_followup(text, history_text=history_text):
        return True
    from app.services.admin_client.security.security_followup import is_security_history_context

    if is_security_history_context(history_text) and (
        message_targets_incidents(text) or is_security_report_message(text)
    ):
        return False
    if message_targets_incidents(text):
        return False
    if is_user_scoped_logs_message(text):
        return False
    if re.search(r"\bmission\b", text, re.I) and re.search(
        r"\blogs?\b|journal|r[eé]sum[eé]|synth[eè]se", text, re.I
    ):
        return False
    if is_logs_history_context(history_text) and _message_targets_logs(text):
        return True
    if not is_logs_workspace(text, history_text=history_text):
        return False

    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if wants_pdf_format(text) and is_users_workspace(text, history_text=history_text):
        return False

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False
    if is_dashboard_report_message(text):
        return False
    if should_route_reports(text, history_text=history_text):
        return False

    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request

    if re.search(r"\b(colis|suivi|tracking|shipment|package)\b", text, re.I):
        if is_admin_shipment_pdf_request(text) or wants_pdf_format(text):
            return False
    return True


def should_route_users(message: str, *, history_text: str = "") -> bool:
    """Tour gestion utilisateurs admin — après reports, avant PDF colis."""
    text = (message or "").strip()
    from app.services.admin_client.email.email_patterns import (
        is_send_user_email_message,
        is_users_action_email_combo,
    )
    from app.services.admin_client.email.email_followup import (
        is_email_clarify_followup,
        is_suspend_email_clarify_context,
    )

    if is_users_action_email_combo(text):
        return True
    if is_suspend_email_clarify_context(history_text) and is_email_clarify_followup(
        text, history_text=history_text
    ):
        return True
    if is_send_user_email_message(text):
        return False
    if is_logs_workspace(text, history_text=history_text) and not is_user_scoped_logs_message(text):
        return False
    if is_tickets_workspace(text, history_text=history_text):
        return False
    if not is_users_workspace(text, history_text=history_text):
        return False

    from app.services.admin_client.users.users_followup import (
        extract_user_ref,
        is_users_history_context,
    )

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        if not (is_users_history_context(history_text) and extract_user_ref(text, history_text=history_text)):
            return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False
    if is_dashboard_report_message(text):
        return False
    if should_route_reports(text, history_text=history_text):
        return False
    if is_dashboard_users_kpi(text) and not re.search(
        r"\b(suspend|supprim|logs?|fiche|d[eé]tail|permissions?|liste|list|renomm|mot\s+de\s+passe|comptes?)\b",
        text,
        re.I,
    ):
        if should_route_dashboard(text, history_text=history_text):
            return False

    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request

    if re.search(r"\b(colis|suivi|tracking|shipment|package)\b", text, re.I):
        if is_admin_shipment_pdf_request(text) or wants_pdf_format(text):
            return False
    return True


def should_route_tickets(message: str, *, history_text: str = "") -> bool:
    """Tour tickets support admin — après users, avant PDF colis."""
    text = (message or "").strip()
    from app.services.admin_client.email.email_patterns import is_tickets_action_email_combo

    if is_tickets_action_email_combo(text):
        return True
    if _message_targets_logs(text):
        return False
    if message_targets_incidents(text):
        return False
    if is_security_history_context(history_text) and not re.search(r"\bticket", text, re.I):
        return False
    if is_logs_history_context(history_text) and not re.search(r"\bticket", text, re.I):
        return False
    if not is_tickets_workspace(text, history_text=history_text):
        return False

    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if wants_pdf_format(text) and is_users_workspace(text, history_text=history_text):
        return False

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        if not (is_tickets_history_context(history_text) and extract_ticket_ref(text, history_text=history_text)):
            return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False
    if is_dashboard_report_message(text):
        return False
    if should_route_reports(text, history_text=history_text):
        return False
    if should_route_users(text, history_text=history_text):
        return False
    if is_dashboard_users_kpi(text) and should_route_dashboard(text, history_text=history_text):
        return False

    from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request

    if re.search(r"\b(colis|suivi|tracking|shipment|package)\b", text, re.I):
        if is_admin_shipment_pdf_request(text) or wants_pdf_format(text):
            return False
    return True


def should_route_missions(message: str, *, history_text: str = "") -> bool:
    """Tour Mission Control admin — après logs plateforme, avant tickets."""
    text = (message or "").strip()
    from app.services.admin_client.missions.missions_followup import is_missions_followup_message
    from app.services.admin_client.missions.missions_pending import is_missions_action_pending
    from app.services.admin_client.missions.missions_workspace import (
        is_missions_workspace,
        should_exclude_platform_logs,
    )

    if should_exclude_platform_logs(text):
        return False
    if is_missions_action_pending(history_text=history_text):
        return True
    if is_missions_followup_message(text, history_text=history_text):
        return True
    if not is_missions_workspace(text, history_text=history_text):
        return False

    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        return False
    if is_admin_explicit_notification(text):
        return False
    if is_pdf_clarify_choice_message(text):
        return False
    if is_dashboard_report_message(text):
        return False
    if should_route_reports(text, history_text=history_text) and not re.search(
        r"\bmission\b", text, re.I
    ):
        return False
    if should_route_security(text, history_text=history_text):
        return False
    if should_route_logs(text, history_text=history_text):
        return False
    return True


def should_route_email(message: str, *, history_text: str = "") -> bool:
    """Tour envoi e-mail admin → utilisateur (Phase 1 standalone)."""
    text = (message or "").strip()
    from app.services.admin_client.email.email_patterns import (
        is_admin_action_email_combo,
        is_admin_recipients_email,
        is_bulk_email_message,
        is_send_user_email_message,
    )
    from app.services.admin_client.email.email_followup import is_email_clarify_pending
    from app.services.admin_client.email.email_pending import is_email_send_pending

    if is_email_send_pending(history_text=history_text):
        return True
    if is_email_clarify_pending(history_text=history_text):
        return True
    if is_admin_action_email_combo(text):
        return False
    if not text or is_bulk_email_message(text) or is_admin_recipients_email(text):
        return False
    if is_admin_explicit_notification(text):
        return False
    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        if not is_send_user_email_message(text):
            return False
    if _wants_explicit_file_export(text) and not is_send_user_email_message(text):
        return False
    if is_send_user_email_message(text):
        return True
    return False


def should_route_document_followup(message: str) -> bool:
    """Document followup admin seulement si pas d'intent métier explicite."""
    text = (message or "").strip()
    if not text:
        return False
    if is_admin_explicit_notification(text):
        return False
    if _wants_explicit_file_export(text):
        return False
    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        return False
    return is_document_followup_question(text)
