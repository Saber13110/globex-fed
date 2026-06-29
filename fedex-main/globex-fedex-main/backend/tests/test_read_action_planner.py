"""Tests planificateur lecture Globex Agent (routeur copilot)."""

from unittest.mock import patch

from app.services.ai_assistant.tool_planner import plan_export_tools
from app.services.ai_assistant.tool_registry import resolve_handler
from app.services.globex_agent.local_replies import (
    is_capabilities_request,
    is_greeting_message,
)
from app.services.globex_agent.read_action_planner import (
    is_capabilities_help_message,
    is_capabilities_intent,
    plan_read_action_tools,
)
from app.services.globex_agent.scan_action_planner import plan_scan_action_tools
from app.services.globex_agent.security_action_planner import plan_security_action_tools
from app.services.gpt.intent_classifier import INTENT_CAPABILITIES, INTENT_GENERAL, classify_intent
from app.services.gpt.orchestrator import SLUG_ADMIN


def test_greeting_jarvis_prefix():
    assert is_greeting_message("bonjour jarvis")


def test_resolve_handler_users_summary():
    assert resolve_handler("get_users_summary") == "analyze_users"


def test_capabilities_help_comment():
    assert is_capabilities_help_message("comment tu peux m'aider")
    assert is_capabilities_request("comment tu peux m'aider")


def test_capabilities_variants():
    assert is_capabilities_request("comment tu peux m aider")
    assert is_capabilities_request("comment tu peux m'aider")
    assert is_capabilities_request("how can you help")
    assert is_capabilities_request("que peux-tu faire")
    assert classify_intent("comment tu peux m'aider", SLUG_ADMIN).intent == INTENT_CAPABILITIES


def test_capabilities_intent_que_peux_tu_faire():
    assert is_capabilities_intent("que peux-tu faire")


def test_ollama_skip_reply_capabilities():
    from app.services.globex_agent.local_replies import ollama_skip_reply

    reply = ollama_skip_reply(lang="fr", message="comment tu peux m'aider", agent_mode=True)
    assert "Jarvis" in reply
    assert "colis" in reply.lower() or "tickets" in reply.lower()


def test_ollama_skip_reply_vague_question():
    from app.services.globex_agent.local_replies import ollama_skip_reply

    reply = ollama_skip_reply(lang="fr", message="explique la météo", agent_mode=True)
    assert "Ollama" in reply
    assert "tickets" in reply.lower() or "logs" in reply.lower()


def test_ollama_readiness_cache():
    from app.services.globex_agent import ollama_readiness as mod

    with patch.object(mod, "_probe_ollama_inference", return_value=True) as probe:
        mod.invalidate_ollama_readiness_cache()
        assert mod.ollama_inference_ready(force=True) is True
        assert mod.ollama_inference_ready() is True
        assert probe.call_count == 1
        assert mod.ollama_inference_ready() is True
        assert probe.call_count == 1


def test_plan_read_tickets_ouverts():
    intent = classify_intent("montre les tickets ouverts", SLUG_ADMIN).intent
    plan = plan_read_action_tools("montre les tickets ouverts", intent)
    assert plan
    names = [p[0] for p in plan]
    assert "analyze_tickets" in names


def test_plan_read_filters_export():
    intent = classify_intent("exporte les logs en PDF", SLUG_ADMIN).intent
    plan = plan_read_action_tools("exporte les logs en PDF", intent)
    assert plan is None


def test_plan_read_bonjour_empty():
    plan = plan_read_action_tools("bonjour", INTENT_GENERAL)
    assert plan is None


def test_plan_read_kpi_platform():
    plan = plan_read_action_tools("synthèse KPI plateforme", INTENT_GENERAL)
    assert plan
    assert plan[0][0] == "get_platform_stats"


def test_regression_security_attack():
    plan = plan_security_action_tools("dernière tentative d'attaque")
    assert plan == [("analyze_security", {"limit": 1})]


def test_regression_scan_dormant():
    plan = plan_scan_action_tools("comptes dormants 30 jours")
    assert plan and plan[0][0] == "scan_dormant_accounts"


def test_regression_export_logs():
    plan = plan_export_tools("exporte les logs 24h en PDF", None)
    assert plan and plan[0][0].startswith("export_activity_logs")
