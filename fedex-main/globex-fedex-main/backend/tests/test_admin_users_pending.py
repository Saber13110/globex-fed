"""Tests confirmation chat actions utilisateurs."""

from __future__ import annotations

from app.services.admin_client.users.users_pending import (
    build_users_pending_marker,
    is_users_action_pending,
    is_users_confirm_message,
    parse_pending_user_action,
)


def test_users_confirm_detection():
    assert is_users_confirm_message("oui")
    assert is_users_confirm_message("confirme")
    assert not is_users_confirm_message("peut-être")


def test_pending_marker_roundtrip():
    marker = build_users_pending_marker("suspend", 3, {"reason": "test"})
    text = "Confirmez?" + marker
    assert is_users_action_pending(last_bot_text=text)
    pending = parse_pending_user_action(text)
    assert pending is not None
    assert pending.action == "suspend"
    assert pending.user_id == 3
    assert pending.payload.get("reason") == "test"
