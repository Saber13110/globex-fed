"""Tests Phase 9 — lecture documents client."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.document_text_extractor import DocumentExtractError
from app.services.llm.providers import LlmProviderError
from app.services.client_phase9.capabilities import CAP_DOCUMENT_READ, has_document_read_capability
from app.services.client_phase9.document_reader import (
    build_document_context,
    resolve_attachment,
    try_document_read_turn,
)
from app.services.message_attachment import pack_message_text, unpack_message_attachment


def test_has_document_read_capability():
    with patch("app.services.client_phase9.capabilities.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(
            client_agent_capabilities=f"chat,{CAP_DOCUMENT_READ}",
        )
        assert has_document_read_capability()


def test_resolve_attachment_image():
    att = resolve_attachment(
        attachment_base64="abc123",
        attachment_mime_type="image/png",
        file_name="label.png",
    )
    assert att is not None
    assert att.kind == "image"
    assert att.file_name == "label.png"


def test_resolve_attachment_pdf():
    att = resolve_attachment(
        attachment_base64="abc123",
        attachment_mime_type="application/pdf",
        file_name="facture.pdf",
    )
    assert att is not None
    assert att.kind == "document"


def test_build_document_context():
    ctx = build_document_context(
        caption="Résume ce document",
        filename="facture.pdf",
        extracted_text="Total: 100 EUR",
    )
    assert "DOCUMENT EXTRAIT" in ctx
    assert "facture.pdf" in ctx
    assert "Total: 100 EUR" in ctx
    assert "Résume ce document" in ctx


def test_pack_unpack_document_attachment():
    raw = pack_message_text(
        "Analyse",
        image_base64="Zm9v",
        image_mime_type="application/pdf",
        file_name="doc.pdf",
    )
    text, b64, mime, name, kind = unpack_message_attachment(raw)
    assert text == "Analyse"
    assert b64 == "Zm9v"
    assert mime == "application/pdf"
    assert name == "doc.pdf"
    assert kind == "document"


def test_pack_unpack_legacy_image():
    raw = pack_message_text(
        "Photo",
        image_base64="YmFy",
        image_mime_type="image/jpeg",
    )
    text, b64, mime, name, kind = unpack_message_attachment(raw)
    assert text == "Photo"
    assert mime == "image/jpeg"
    assert kind == "image"


@patch("app.services.client_phase9.document_reader.has_document_read_capability", return_value=True)
@patch("app.services.client_phase9.document_reader.call_gemini_document", return_value="Synthèse du PDF.")
@patch("app.services.client_phase9.document_reader.extract_text_from_bytes", return_value="Ligne facture 42")
def test_try_document_read_pdf(mock_extract, mock_gemini, _cap):
    from app.services.client_phase9.document_reader import ResolvedAttachment

    pdf_bytes = b"%PDF-1.4 test"
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    att = ResolvedAttachment(
        base64_data=b64,
        mime_type="application/pdf",
        file_name="facture.pdf",
        kind="document",
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=1)
    db = MagicMock()
    turn = try_document_read_turn(
        db,
        user,
        session,
        "Résume",
        1,
        attachment=att,
        ui_language="fr",
        compute_phase2_reply=MagicMock(),
    )
    assert turn is not None
    assert turn["intent"] == "document_read"
    assert turn["source"] == "agent_document"
    assert turn["llm_provider"] == "gemini"
    assert "Synthèse" in turn["reply"]
    mock_gemini.assert_called_once()


@patch("app.services.client_phase9.document_reader.has_document_read_capability", return_value=True)
@patch("app.services.client_phase9.document_reader.extract_text_from_bytes", side_effect=DocumentExtractError("GEMINI_API_KEY"))
def test_try_document_read_image_without_gemini(mock_extract, _cap):
    from app.services.client_phase9.document_reader import ResolvedAttachment

    att = ResolvedAttachment(
        base64_data=base64.b64encode(b"\x89PNG").decode("ascii"),
        mime_type="image/png",
        file_name="scan.png",
        kind="image",
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=1)
    db = MagicMock()
    turn = try_document_read_turn(
        db,
        user,
        session,
        "Lis l'image",
        1,
        attachment=att,
        ui_language="fr",
        compute_phase2_reply=MagicMock(),
    )
    assert turn is not None
    assert turn["intent"] == "document_read_failed"
    assert "GEMINI" in turn["reply"]


@patch("app.services.client_phase9.document_reader.has_document_read_capability", return_value=True)
@patch("app.services.client_phase9.document_reader.call_gemini_document", return_value="880892017122")
@patch("app.services.client_phase9.document_reader.extract_text_from_bytes", return_value="Colis 880892017122")
def test_try_document_read_extract_number_uses_gemini(mock_extract, mock_gemini, _cap):
    from app.services.client_phase9.document_reader import ResolvedAttachment

    compute = MagicMock()
    att = ResolvedAttachment(
        base64_data=base64.b64encode(b"%PDF").decode("ascii"),
        mime_type="application/pdf",
        file_name="etiquette.pdf",
        kind="document",
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=1)
    db = MagicMock()
    turn = try_document_read_turn(
        db,
        user,
        session,
        "extrait le numéro de suivi",
        1,
        attachment=att,
        ui_language="fr",
        compute_phase2_reply=compute,
    )
    assert turn["intent"] == "document_read"
    compute.assert_not_called()
    mock_gemini.assert_called_once()
    assert mock_gemini.call_args.kwargs.get("concise") is True


@patch("app.services.client_phase9.document_reader.has_document_read_capability", return_value=True)
@patch("app.services.client_phase9.document_reader.call_gemini_document")
@patch("app.services.client_phase9.document_reader.extract_text_from_bytes", return_value="Colis 881135077232")
def test_try_document_read_tracking_delegation(mock_extract, mock_gemini, _cap):
    from app.services.client_phase9.document_reader import ResolvedAttachment

    compute = MagicMock(
        return_value=("Suivi OK", "fedex_api", "tracking", "881135077232", None, {"tracking_number": "881135077232"})
    )
    att = ResolvedAttachment(
        base64_data=base64.b64encode(b"%PDF").decode("ascii"),
        mime_type="application/pdf",
        file_name="etiquette.pdf",
        kind="document",
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=1)
    db = MagicMock()
    turn = try_document_read_turn(
        db,
        user,
        session,
        "Où est mon colis ?",
        1,
        attachment=att,
        ui_language="fr",
        compute_phase2_reply=compute,
    )
    assert turn["intent"] == "document_read_tracking"
    compute.assert_called_once()
    assert compute.call_args[0][3] == "Où est mon colis ?"
    mock_gemini.assert_not_called()


@patch("app.services.client_phase9.document_reader.get_settings")
@patch("app.services.client_phase9.document_reader.has_document_read_capability", return_value=True)
@patch("app.services.client_phase9.document_reader.call_gemini_document", return_value="OK")
@patch("app.services.client_phase9.document_reader.extract_text_from_bytes")
def test_try_document_read_truncates_for_llm(mock_extract, mock_gemini, _cap, mock_settings):
    from app.services.client_phase9.document_reader import ResolvedAttachment

    mock_settings.return_value = SimpleNamespace(
        client_document_max_mb=10,
        client_document_max_chars=12000,
        client_document_llm_max_chars=100,
    )
    long_text = "A" * 500
    mock_extract.return_value = long_text
    att = ResolvedAttachment(
        base64_data=base64.b64encode(b"%PDF").decode("ascii"),
        mime_type="application/pdf",
        file_name="long.pdf",
        kind="document",
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=1)
    db = MagicMock()
    try_document_read_turn(
        db,
        user,
        session,
        "Résume",
        1,
        attachment=att,
        ui_language="fr",
        compute_phase2_reply=MagicMock(),
    )
    enriched = mock_gemini.call_args[0][0]
    assert "A" * 60 in enriched
    assert "contenu tronqué" in enriched
    assert "A" * 200 not in enriched


@patch("app.services.client_phase9.document_reader.has_document_read_capability", return_value=True)
@patch(
    "app.services.client_phase9.document_reader.call_gemini_document",
    side_effect=LlmProviderError("Timeout Gemini"),
)
@patch("app.services.client_phase9.document_reader.extract_text_from_bytes", return_value="Texte court")
def test_try_document_read_gemini_failure_message(mock_extract, mock_gemini, _cap):
    from app.services.client_phase9.document_reader import ResolvedAttachment

    att = ResolvedAttachment(
        base64_data=base64.b64encode(b"%PDF").decode("ascii"),
        mime_type="application/pdf",
        file_name="doc.pdf",
        kind="document",
    )
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    session = SimpleNamespace(id=1)
    db = MagicMock()
    turn = try_document_read_turn(
        db,
        user,
        session,
        "Résume",
        1,
        attachment=att,
        ui_language="fr",
        compute_phase2_reply=MagicMock(),
    )
    assert turn["intent"] == "document_read_failed"
    assert "temporairement indisponible" in turn["reply"]


@patch("app.services.client_phase9.capabilities.get_settings")
def test_capability_disabled(mock_settings):
    mock_settings.return_value = SimpleNamespace(client_agent_capabilities="chat")
    assert not has_document_read_capability()


def test_is_document_followup_question():
    from app.services.client_phase9.document_session import is_document_followup_question

    assert is_document_followup_question("extrait le numéro de suivi")
    assert is_document_followup_question("résume le contexte du fichier")
    assert not is_document_followup_question("où est mon colis ?")
    assert not is_document_followup_question("bonjour")


@patch("app.services.client_phase9.document_session.try_document_read_turn")
@patch("app.services.client_phase9.document_session.find_recent_session_attachment")
def test_try_document_followup_turn_with_session_attachment(mock_find, mock_read):
    from app.services.client_phase9.document_reader import ResolvedAttachment
    from app.services.client_phase9.document_session import try_document_followup_turn

    att = ResolvedAttachment(
        base64_data="Zm9v",
        mime_type="application/pdf",
        file_name="doc.pdf",
        kind="document",
    )
    mock_find.return_value = att
    mock_read.return_value = {
        "reply": "880892017122",
        "source": "agent_document",
        "intent": "document_read",
        "tracking_number": None,
        "llm_provider": "gemini",
        "shipment": None,
        "export_download": None,
    }
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    turn = try_document_followup_turn(
        db,
        user,
        session,
        "extrait le numéro",
        99,
        ui_language="fr",
        compute_phase2_reply=MagicMock(),
    )
    assert turn is not None
    assert turn["reply"] == "880892017122"
    mock_find.assert_called_once_with(db, 42, exclude_message_id=99)
    mock_read.assert_called_once()


def test_try_document_followup_turn_without_attachment_returns_none():
    from app.services.client_phase9.document_session import try_document_followup_turn

    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()
    with patch(
        "app.services.client_phase9.document_session.find_recent_session_attachment",
        return_value=None,
    ):
        turn = try_document_followup_turn(
            db,
            user,
            session,
            "extrait le numéro",
            99,
            ui_language="fr",
            compute_phase2_reply=MagicMock(),
        )
    assert turn is None
