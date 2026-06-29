"""Tests confirmation chat partage rapport."""

from __future__ import annotations

from app.services.admin_client.reports.reports_share_pending import (
    build_share_pending_marker,
    is_share_confirm_message,
    is_share_pending,
    parse_pending_share,
)


def test_share_confirm_detection():
    assert is_share_confirm_message("oui")
    assert is_share_confirm_message("confirme")
    assert not is_share_confirm_message("peut-être")


def test_pending_marker_roundtrip():
    marker = build_share_pending_marker(7, ["alice@test.com"])
    text = "Confirmez?" + marker
    assert is_share_pending(last_bot_text=text)
    pending = parse_pending_share(text)
    assert pending is not None
    assert pending.run_id == 7
    assert pending.recipient_emails == ["alice@test.com"]
