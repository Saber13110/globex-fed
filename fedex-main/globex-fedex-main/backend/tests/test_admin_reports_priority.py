"""Tests gate reports vs dashboard/suivi/PDF."""

from __future__ import annotations

from app.services.admin_client.intent_priority import should_route_reports


def test_should_route_reports_preview():
    assert should_route_reports("Prévisualise le dernier export")


def test_should_route_reports_list():
    assert should_route_reports("Montre les exports récents")


def test_should_route_reports_list_all_reports():
    assert should_route_reports("liste moi tous les reports")


def test_should_route_reports_share():
    assert should_route_reports("Partage le rapport à alice@test.com")


def test_should_not_route_delay_report_dashboard():
    assert not should_route_reports("Prépare un rapport des retards en pdf")


def test_should_not_route_tracking():
    assert not should_route_reports("suivi 817725683025")


def test_should_not_route_shipment_pdf():
    assert not should_route_reports("exporte le suivi colis en pdf")
