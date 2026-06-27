"""Priorité format explicite Excel vs PDF (fix « fichier excel » → PDF)."""

from app.services.client_phase3.excel_postprocess import wants_excel_format
from app.services.client_phase3.export_intent import (
    has_explicit_excel_format,
    has_explicit_pdf_format,
    is_excel_export_intent,
    is_pdf_export_intent,
)
from app.services.client_phase3.pdf_postprocess import wants_pdf_format


def test_fichier_excel_does_not_trigger_pdf():
    msg = "je veux les infos dans un fichier excel"
    assert has_explicit_excel_format(msg)
    assert not has_explicit_pdf_format(msg)
    assert not is_pdf_export_intent(msg)
    assert not wants_pdf_format(msg)
    assert is_excel_export_intent(msg)
    assert wants_excel_format(msg)


def test_pdf_followup_still_works():
    assert wants_pdf_format("mets ces infos en pdf")
    assert wants_excel_format("ces infos en excel")


def test_fichier_pdf_still_triggers_pdf():
    msg = "un fichier pdf du colis"
    assert wants_pdf_format(msg)
    assert not wants_excel_format(msg)


def test_explicit_pdf_blocks_excel():
    assert not wants_excel_format("exporte en pdf")
    assert wants_pdf_format("exporte en pdf")


def test_bonjour_no_export():
    assert not wants_pdf_format("Bonjour")
    assert not wants_excel_format("Bonjour")
