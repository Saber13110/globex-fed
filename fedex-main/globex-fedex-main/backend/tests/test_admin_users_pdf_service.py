"""Tests export PDF utilisateurs."""

from __future__ import annotations

from unittest.mock import patch

from app.services.admin_client.users.users_pdf import build_users_pdf_export


@patch("app.services.admin_client.users.users_pdf.build_text_pdf_download")
def test_pdf_suspended_filename(mock_pdf):
    mock_pdf.return_value = {"url": "/dl/1", "filename": "x.pdf"}
    note, dl = build_users_pdf_export(
        1,
        2,
        export_kind="list",
        processed={
            "users": [
                {
                    "id": 1,
                    "full_name": "Bob",
                    "email": "bob@test.com",
                    "role": "client",
                    "status": "suspended",
                }
            ]
        },
        lang="fr",
        status_filter="suspended",
    )
    assert dl is not None
    assert dl["filename"] == "users_suspended.pdf"
    assert "prêt" in note.lower() or "PDF" in note


def test_pdf_empty_list_refused():
    note, dl = build_users_pdf_export(
        1,
        2,
        export_kind="list",
        processed={"users": []},
        lang="fr",
        status_filter="suspended",
    )
    assert dl is None
    assert "PDF non généré" in note
