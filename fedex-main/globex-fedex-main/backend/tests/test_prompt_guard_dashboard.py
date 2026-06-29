"""Prompt guard — requêtes dashboard admin non bloquées."""

from __future__ import annotations

from unittest.mock import patch

from app.services.prompt_guard_service import RiskLevel, assess_text, assess_user_message


_DASHBOARD_MSG = "Donne-moi un résumé rapide de l'activité récente."


@patch("app.services.client_phase12.capabilities.smart_guard_enabled", return_value=False)
def test_dashboard_activity_not_blocked_legacy_guard(_mock_sg):
    result = assess_text(_DASHBOARD_MSG)
    assert result.level != RiskLevel.block, result.reasons


@patch("app.services.client_phase12.capabilities.smart_guard_enabled", return_value=False)
def test_dashboard_activity_allowed_user_message(_mock_sg):
    result = assess_user_message(_DASHBOARD_MSG)
    assert result.level == RiskLevel.ok, result.reasons


@patch("app.services.client_phase12.capabilities.smart_guard_enabled", return_value=True)
def test_dashboard_activity_allowed_smart_guard(_mock_sg):
    result = assess_user_message(_DASHBOARD_MSG)
    assert result.level == RiskLevel.ok, result.reasons
