"""Tests Phase 7 — export PDF/Excel par mail."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.client_phase6.watch_intent import is_watch_workspace
from app.services.client_phase7.capabilities import CAP_EMAIL_EXPORT, has_email_export_capability
from app.services.client_phase7.export_email_hook import apply_export_email_delivery, finalize_export_delivery
from app.services.client_phase7.export_email_intent import (
    is_export_email_only_followup,
    wants_export_by_email,
)
from app.services.client_phase7.export_session_pointer import get_session_export_pointer, remember_session_export


def test_wants_export_by_email_pdf():
    assert wants_export_by_email("Exporte le PDF du colis par mail")
    assert wants_export_by_email("Excel suivi par email")


def test_wants_export_by_email_false_for_live_track():
    assert not wants_export_by_email("Où est mon colis 881135077232 ?")


def test_is_export_email_only_followup():
    assert is_export_email_only_followup("Envoie-le par mail")
    assert not is_export_email_only_followup("Exporte en PDF")


def test_watch_workspace_excludes_export_mail():
    assert not is_watch_workspace("PDF colis par mail")
    assert not is_watch_workspace("Exporte en excel par email")
    assert is_watch_workspace("Préviens-moi par mail pour le colis 881135077232")


@patch("app.services.client_phase7.capabilities.get_settings")
def test_has_email_export_capability(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_capabilities=f"chat,pdf,{CAP_EMAIL_EXPORT}",
    )
    assert has_email_export_capability()


@patch("app.services.client_phase7.export_email_hook.has_email_export_capability", return_value=True)
@patch("app.services.client_phase7.export_email_hook.wants_export_by_email", return_value=True)
@patch("app.services.client_phase7.export_email_hook.is_email_configured", return_value=True)
@patch("app.services.client_phase7.export_email_hook.send_client_export_email", return_value=True)
def test_apply_export_email_delivery_sends(mock_send, _smtp, _want, _cap):
    user = SimpleNamespace(id=1, email="u@test.com", full_name="Test", preferred_language="fr")
    spec = {"export_token": "abc123", "filename": "doc.pdf", "format": "pdf"}
    suffix, sent = apply_export_email_delivery(
        user,
        session_id=9,
        message="pdf par mail",
        file_bytes=b"%PDF-1.4",
        filename="doc.pdf",
        fmt="pdf",
        export_download_spec=spec,
        doc_label="Test PDF",
    )
    assert sent is True
    assert "u@test.com" in suffix
    mock_send.assert_called_once()
    ptr = get_session_export_pointer(9)
    assert ptr is not None
    assert ptr.export_token == "abc123"


@patch("app.services.client_phase7.export_email_hook.has_email_export_capability", return_value=True)
@patch("app.services.client_phase7.export_email_hook.wants_export_by_email", return_value=False)
def test_apply_export_email_skips_without_intent(_want, _cap):
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    suffix, sent = apply_export_email_delivery(
        user,
        session_id=1,
        message="pdf seulement",
        file_bytes=b"x",
        filename="a.pdf",
        fmt="pdf",
        export_download_spec={"export_token": "t"},
        doc_label="Doc",
    )
    assert sent is False
    assert suffix == ""


@patch("app.services.client_phase7.export_email_hook.has_email_export_capability", return_value=True)
@patch("app.services.client_phase7.export_email_hook.wants_export_by_email", return_value=True)
@patch("app.services.client_phase7.export_email_hook.is_email_configured", return_value=True)
@patch("app.services.client_phase7.export_email_hook.send_client_export_email", return_value=True)
def test_finalize_export_delivery_preserves_spec(_mock_send, _smtp, _want, _cap):
    user = SimpleNamespace(id=1, email="u@test.com", preferred_language="fr")
    spec = {"export_token": "tok", "filename": "f.pdf", "format": "pdf"}
    reply, out = finalize_export_delivery(
        user,
        1,
        "par mail",
        "Voici votre PDF.",
        spec,
        b"bytes",
        "f.pdf",
        "pdf",
        "Doc",
    )
    assert out is spec
    assert "Voici votre PDF" in reply
    assert "u@test.com" in reply


@patch("app.services.client_phase7.capabilities.get_settings")
def test_try_export_email_only_turn_from_cache(mock_settings):
    from app.services.client_phase7.export_email_followup import try_export_email_only_turn

    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="email_export,pdf",
    )
    remember_session_export(42, export_token="cachedtoken", fmt="pdf", filename="n.pdf")

    user = SimpleNamespace(id=7, email="u@test.com", full_name="T", preferred_language="fr")
    session = SimpleNamespace(id=42)
    db = MagicMock()

    cached = {"pdf_bytes": b"%PDF", "filename": "n.pdf", "export_token": "cachedtoken"}
    with patch(
        "app.services.client_phase7.export_email_followup.get_owner_export_dataset",
        return_value=cached,
    ):
        with patch(
            "app.services.client_phase7.export_email_followup.finalize_export_delivery",
            return_value=("Envoyé.", {"export_token": "cachedtoken"}),
        ) as mock_fin:
            turn = try_export_email_only_turn(db, user, session, "envoie par mail", "fr")

    assert turn is not None
    assert turn["intent"] == "export_email_delivery"
    mock_fin.assert_called_once()
