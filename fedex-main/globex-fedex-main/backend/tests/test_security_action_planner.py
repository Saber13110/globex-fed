"""Tests planificateur sécurité Globex Agent."""

from app.services.globex_agent.security_action_planner import (
    is_security_read_request,
    plan_security_action_tools,
)


def test_last_attack_routes_analyze_security_limit_1():
    msg = "je veux que tu me donne la dernier tentative d'attaque"
    plan = plan_security_action_tools(msg)
    assert plan == [("analyze_security", {"limit": 1})]
    assert is_security_read_request(msg)


def test_security_alerts():
    plan = plan_security_action_tools("montre les alertes sécurité")
    assert plan == [("get_security_alerts", {})]


def test_suspicious_logs_default_24h():
    plan = plan_security_action_tools("analyse les logs suspects")
    assert plan == [("analyze_suspicious_logs", {"hours": 24, "limit": 15})]


def test_security_scan():
    plan = plan_security_action_tools("lance un scan sécurité")
    assert plan == [("run_security_scan", {})]


def test_greeting_not_security():
    assert plan_security_action_tools("bonjour") is None
    assert not is_security_read_request("bonjour")


def test_attack_without_last_uses_higher_limit():
    plan = plan_security_action_tools("liste les tentatives d'attaque")
    assert plan == [("analyze_security", {"limit": 10})]
