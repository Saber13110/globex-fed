"""Tests priorité dashboard vs suivi/PDF/notifs."""

from __future__ import annotations

from app.services.admin_client.intent_priority import should_route_dashboard


def test_should_route_dashboard_kpi():
    assert should_route_dashboard("Résume l'état de la plateforme aujourd'hui")


def test_should_not_route_tracking_number():
    assert not should_route_dashboard("suivi colis 817725683025")


def test_should_not_route_notifications():
    assert not should_route_dashboard("mes notifications non lues")


def test_should_not_route_shipment_pdf():
    assert not should_route_dashboard("génère ces infos en pdf")


def test_should_not_route_pdf_colis_explicit():
    assert not should_route_dashboard("exporte le suivi colis en pdf")


def test_should_not_route_pdf_clarify_choice():
    assert not should_route_dashboard("1")


def test_should_route_delay_report_before_pdf_conflict():
    assert should_route_dashboard("Prépare un rapport des retards en pdf")


def test_should_route_activity_resume():
    assert should_route_dashboard("Donne-moi un résumé rapide de l'activité récente")


def test_should_route_platform_report():
    assert should_route_dashboard("rapport plateforme KPI")
