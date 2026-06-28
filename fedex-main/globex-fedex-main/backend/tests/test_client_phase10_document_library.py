"""Tests Phase 10 — bibliothèque documents client."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.client_phase7.export_session_pointer import clear_all_session_export_pointers

from app.services.client_phase10.capabilities import CAP_DOCUMENT_LIBRARY, has_document_library_capability
from app.services.client_phase10.document_catalog import (
    DocumentCatalogItem,
    _classify_blob,
    filter_document_catalog,
    format_catalog_list,
)
from app.services.client_phase10.document_download import build_download_spec
from app.services.client_phase10.router import try_client_document_library_turn


@pytest.fixture(autouse=True)
def _isolate_export_session_pointers():
    clear_all_session_export_pointers()
    yield
    clear_all_session_export_pointers()


def _item(doc_type: str, *, tn: str = "880892017122", sid: int = 5) -> DocumentCatalogItem:
    return DocumentCatalogItem(
        id=f"{doc_type}-{tn}-{sid}",
        title=f"Test {doc_type} — {tn}",
        doc_type=doc_type,  # type: ignore[arg-type]
        tracking_number=tn,
        session_id=sid,
        history_id=1,
        created_at=datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc),
    )


def test_classify_blob_matches_documents_page():
    assert _classify_blob("Export excel du suivi") == "export"
    assert _classify_blob("Preuve de livraison POD") == "proof"
    assert _classify_blob("Voici le pdf facture") == "report"
    assert _classify_blob("envoie moi le rapport du jour") == "report"
    assert _classify_blob("Export historique FedEx") == "export"
    assert _classify_blob("Où est mon colis") is None


def test_filter_document_catalog_by_type_and_query():
    items = [_item("export"), _item("proof", tn="881135077232")]
    filtered = filter_document_catalog(items, q="881135", type_filter="proof")
    assert len(filtered) == 1
    assert filtered[0].doc_type == "proof"


def test_build_download_spec_export_report_proof():
    export_spec = build_download_spec(_item("export"))
    assert export_spec["format"] == "xlsx"
    assert export_spec["preset"] == "tracking"
    assert export_spec["include_events"] is False

    report_item = DocumentCatalogItem(
        id="report-tn-5",
        title="Rapport — test",
        doc_type="report",
        tracking_number="880892017122",
        session_id=5,
        history_id=1,
        created_at=_item("export").created_at,
        source_text="envoie moi le rapport du jour",
    )
    report_spec = build_download_spec(report_item)
    assert report_spec["format"] == "pdf"
    assert report_spec["preset"] == "tracking"

    proof_spec = build_download_spec(_item("proof"))
    assert proof_spec["preset"] == "pod"
    assert proof_spec["format"] == "pdf"


@patch("app.services.client_phase7.export_session_pointer.get_session_export_pointer")
def test_build_download_spec_uses_session_pointer(mock_pointer):
    from types import SimpleNamespace as NS

    mock_pointer.return_value = NS(
        export_token="cachedtoken",
        fmt="pdf",
        filename="rapport-jour.pdf",
    )
    item = DocumentCatalogItem(
        id="session-42",
        title="envoie moi le rapport du jour",
        doc_type="report",
        tracking_number=None,
        session_id=42,
        history_id=None,
        created_at=_item("export").created_at,
        source_text="envoie moi le rapport du jour",
    )
    spec = build_download_spec(item)
    assert spec["export_token"] == "cachedtoken"
    assert spec["format"] == "pdf"
    assert spec["filename"] == "rapport-jour.pdf"


def test_format_catalog_list_numbered():
    text = format_catalog_list([_item("export")], intro="Voici vos documents :")
    assert "1. Test export" in text
    assert "télécharge le 1" in text


@patch("app.services.client_phase10.router.has_document_library_capability", return_value=True)
@patch("app.services.client_phase10.router.build_document_catalog")
def test_list_documents_no_export_download(mock_build, _cap):
    mock_build.return_value = [_item("export")]
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_client_document_library_turn(
        db, user, session, "liste mes documents", 1, ui_language="fr"
    )
    assert turn is not None
    assert turn["intent"] == "list_documents"
    assert turn["export_download"] is None
    assert "1." in turn["reply"]


@patch("app.services.client_phase10.router.has_document_library_capability", return_value=True)
@patch("app.services.client_phase10.router._catalog_from_last_list")
def test_download_document_by_index(mock_catalog, _cap):
    mock_catalog.return_value = [_item("export")]
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_client_document_library_turn(
        db, user, session, "télécharge le 1", 2, ui_language="fr"
    )
    assert turn is not None
    assert turn["intent"] == "download_document"
    assert turn["export_download"] is not None
    assert turn["export_download"]["format"] == "xlsx"


@patch("app.services.client_phase10.router.has_document_library_capability", return_value=True)
@patch("app.services.client_phase10.router.build_document_catalog")
def test_list_all_account_documents(mock_build, _cap):
    mock_build.return_value = [_item("export")]
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_client_document_library_turn(
        db, user, session, "tous les documents de mon compte", 1, ui_language="fr"
    )
    assert turn is not None
    assert turn["intent"] == "list_documents"
    assert "1." in turn["reply"]


@patch("app.services.client_phase10.router.has_document_library_capability", return_value=True)
@patch("app.services.client_phase10.router.build_document_catalog")
def test_list_sidebar_documents(mock_build, _cap):
    mock_build.return_value = [_item("report")]
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_client_document_library_turn(
        db, user, session, "documents du sidebar", 1, ui_language="fr"
    )
    assert turn is not None
    assert turn["intent"] == "list_documents"


@patch("app.services.client_phase10.router.has_document_library_capability", return_value=True)
def test_conversations_request_returns_none(_cap):
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_client_document_library_turn(
        db, user, session, "liste mes conversations", 1, ui_language="fr"
    )
    assert turn is None


@patch("app.services.client_phase10.capabilities.get_settings")
def test_capability_disabled(mock_settings):
    mock_settings.return_value = SimpleNamespace(client_agent_capabilities="chat")
    assert not has_document_library_capability()


@patch("app.services.client_phase10.capabilities.get_settings")
def test_has_document_library_capability(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_capabilities=f"chat,{CAP_DOCUMENT_LIBRARY}",
    )
    assert has_document_library_capability()
