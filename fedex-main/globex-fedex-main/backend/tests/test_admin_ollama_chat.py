"""Tests architecture client-like — Globex Agent admin."""

from unittest.mock import MagicMock, patch

from app.services.globex_agent.admin_chat import admin_ollama_chat
from app.services.globex_agent.routers.executor import plan_to_tool_calls
from app.services.globex_agent.routers.platform_router import plan_admin_platform_task
from app.services.globex_agent.tool_catalog import tools_for_admin_task
from app.services.llm.providers import LlmProviderError


def test_tools_for_admin_task_subset():
    tools = tools_for_admin_task("analyze_security")
    assert "analyze_security" in tools
    assert len(tools) <= 12


def test_plan_to_tool_calls_export_logs():
    calls = plan_to_tool_calls({"task_type": "export_logs", "answers": {"hours": 48, "format": "pdf"}})
    assert calls
    assert calls[0][0] == "export_activity_logs_pdf"
    assert calls[0][1]["hours"] == 48


def test_plan_admin_platform_task_conversation_returns_none():
    raw = '{"task_type":"conversation","ready_to_execute":false}'
    with patch(
        "app.services.globex_agent.routers.platform_router.call_ollama_agent_plan",
        return_value=raw,
    ):
        assert plan_admin_platform_task("bonjour") is None


def test_plan_admin_platform_task_analyze_tickets():
    raw = (
        '{"task_type":"analyze_tickets","ready_to_execute":true,'
        '"assistant_intro":"Voici les tickets.","answers":{}}'
    )
    with patch(
        "app.services.globex_agent.routers.platform_router.call_ollama_agent_plan",
        return_value=raw,
    ):
        plan = plan_admin_platform_task("tickets ouverts")
    assert plan is not None
    assert plan["task_type"] == "analyze_tickets"


@patch("app.services.globex_agent.admin_chat.httpx.Client")
@patch("app.services.globex_agent.admin_chat.get_settings")
def test_admin_ollama_chat_simple_uses_generate(mock_settings, mock_client_cls):
    settings = MagicMock()
    settings.llm_enabled = True
    settings.globex_simple_mode = True
    settings.ollama_base_url = "http://127.0.0.1:11434"
    settings.ollama_model = "llama3.2:3b-instruct"
    settings.ollama_timeout_seconds = 90
    mock_settings.return_value = settings

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "Bonjour, je suis Jarvis."}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    reply = admin_ollama_chat("bonjour", ui_language="fr")
    assert "Jarvis" in reply
    call_args = mock_client.post.call_args
    assert "/api/generate" in call_args[0][0]


@patch("app.services.globex_agent.admin_chat.httpx.Client")
@patch("app.services.globex_agent.admin_chat.get_settings")
def test_admin_ollama_chat_full_mode_uses_chat(mock_settings, mock_client_cls):
    settings = MagicMock()
    settings.llm_enabled = True
    settings.globex_simple_mode = False
    settings.ollama_base_url = "http://127.0.0.1:11434"
    settings.ollama_model = "qwen2.5:7b-instruct"
    settings.ollama_timeout_seconds = 60
    mock_settings.return_value = settings

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"message": {"content": "Bonjour, je suis Jarvis."}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    reply = admin_ollama_chat("bonjour", ui_language="fr", agent_mode=True)
    assert "Jarvis" in reply
    call_args = mock_client.post.call_args
    assert "/api/chat" in call_args[0][0]


@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.admin_ollama_chat", return_value="Salut.")
@patch("app.services.globex_agent.kernel.plan_export_tools")
@patch("app.services.globex_agent.kernel.plan_admin_platform_task")
@patch("app.services.globex_agent.kernel.load_gpt_by_slug")
def test_kernel_simple_mode_skips_planners(
    mock_load_gpt,
    mock_router,
    mock_export,
    mock_chat,
    _log,
):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(db, admin, "bonjour", agent_mode=True, ui_language="fr")
    assert result["tools_used"] == ["ollama_chat"]
    mock_load_gpt.assert_not_called()
    mock_router.assert_not_called()
    mock_export.assert_not_called()
    mock_chat.assert_called_once()


@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.build_tool_context")
@patch("app.services.globex_agent.kernel.load_gpt_by_slug")
@patch("app.services.globex_agent.kernel.plan_client_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_scan_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_security_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_export_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_read_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_admin_platform_task", return_value=None)
@patch("app.services.globex_agent.kernel.admin_ollama_chat", return_value="Je peux aider sur colis, tickets et logs.")
def test_kernel_bonjour_uses_ollama_chat(
    mock_chat,
    mock_router,
    _read,
    _export,
    _security,
    _scan,
    _client,
    mock_load_gpt,
    _ctx,
    _log,
):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    mock_load_gpt.return_value = MagicMock()
    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(db, admin, "bonjour", agent_mode=True, ui_language="fr")
    assert result["tools_used"] == ["ollama_chat"]
    assert "ollama_skip" not in result["tools_used"]
    mock_chat.assert_called_once()


@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.build_tool_context")
@patch("app.services.globex_agent.kernel.load_gpt_by_slug")
@patch("app.services.globex_agent.kernel.plan_client_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_scan_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_security_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_export_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_read_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_admin_platform_task", return_value=None)
@patch(
    "app.services.globex_agent.kernel.admin_ollama_chat",
    return_value="Je gère colis, utilisateurs, tickets, logs et exports.",
)
def test_kernel_tu_peux_faire_quoi_ollama_chat(
    mock_chat,
    mock_router,
    _read,
    _export,
    _security,
    _scan,
    _client,
    mock_load_gpt,
    _ctx,
    _log,
):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    mock_load_gpt.return_value = MagicMock()
    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(db, admin, "tu peux faire quoi", agent_mode=True, ui_language="fr")
    assert result["tools_used"] == ["ollama_chat"]
    assert "capabilities" not in result["tools_used"]
    assert "ollama_skip" not in result["tools_used"]


@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.build_tool_context")
@patch("app.services.globex_agent.kernel.load_gpt_by_slug")
@patch("app.services.globex_agent.kernel.plan_client_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_scan_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_security_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_export_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_read_action_tools", return_value=None)
@patch("app.services.globex_agent.kernel.plan_admin_platform_task", return_value=None)
@patch("app.services.globex_agent.kernel.admin_ollama_chat", side_effect=LlmProviderError("down"))
def test_kernel_ollama_down_attempts_chat_not_skip(
    mock_chat,
    mock_router,
    _read,
    _export,
    _security,
    _scan,
    _client,
    mock_load_gpt,
    _ctx,
    _log,
):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    mock_load_gpt.return_value = MagicMock()
    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    with patch("app.services.globex_agent.kernel.ollama_inference_ready", return_value=False):
        result = run_globex_agent_chat(db, admin, "question vague", agent_mode=True, ui_language="fr")

    assert result["tools_used"] == ["ollama_chat"]
    assert "ollama_skip" not in result["tools_used"]
    assert result["llm_degraded"] is True
    mock_chat.assert_called_once()


def test_resolve_admin_chat_language_french_message_ui_en():
    from app.services.globex_agent.language import resolve_admin_chat_language

    assert resolve_admin_chat_language("comment tu peux aider", "en") == "fr"


def test_resolve_admin_chat_language_english_message_ui_fr():
    from app.services.globex_agent.language import resolve_admin_chat_language

    assert resolve_admin_chat_language("hello how can you help", "fr") == "en"


@patch("app.services.globex_agent.kernel.get_settings")
@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.admin_ollama_chat", return_value="Bonjour !")
def test_kernel_simple_mode_uses_message_language_over_ui(mock_chat, _log, mock_settings):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    settings = MagicMock()
    settings.globex_simple_mode = True
    mock_settings.return_value = settings

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    run_globex_agent_chat(
        db, admin, "comment tu peux aider", agent_mode=True, ui_language="en",
    )

    assert mock_chat.call_args.kwargs["ui_language"] == "fr"


@patch("app.services.jarvis.agent_window_service.write_log")
@patch("app.services.jarvis.agent_window_service.append_message")
@patch("app.services.jarvis.agent_window_service.create_session")
@patch("app.services.jarvis.agent_window_service.get_settings")
@patch("app.services.globex_agent.kernel.run_globex_agent_chat")
def test_agent_window_simple_mode_calls_kernel_direct(
    mock_kernel,
    mock_settings,
    mock_create_session,
    _append,
    _log,
):
    from app.schemas.agent_window import AgentWindowChatRequest
    from app.services.jarvis.agent_window_service import process_agent_window_chat

    settings = MagicMock()
    settings.globex_simple_mode = True
    settings.prompt_guard_enabled = False
    mock_settings.return_value = settings

    session = MagicMock()
    session.id = "sess-1"
    session.jarvis_session_id = None
    mock_create_session.return_value = session

    mock_kernel.return_value = {
        "reply": "Bonjour !",
        "execution_time_ms": 42.0,
    }

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")
    payload = AgentWindowChatRequest(message="bonjour")

    result = process_agent_window_chat(db, admin, payload)

    assert result.engine == "globex-agent"
    assert result.reply == "Bonjour !"
    mock_kernel.assert_called_once()


@patch("app.services.globex_agent.kernel.get_settings")
@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.admin_ollama_chat")
@patch("app.services.globex_agent.kernel.run_admin_client_turn")
def test_kernel_simple_mode_pipeline_handles_tracking(
    mock_pipeline,
    mock_chat,
    _log,
    mock_settings,
):
    """En simple mode, le pipeline admin_client intercepte le suivi avant le bridge/Ollama."""
    from app.services.globex_agent.kernel import run_globex_agent_chat

    settings = MagicMock()
    settings.globex_simple_mode = True
    mock_settings.return_value = settings

    pipeline_result = {
        "reply": "Le colis 123567843932 est en transit.",
        "mode": "jarvis",
        "tools_used": ["admin_client:fedex_api"],
        "intent": "summary",
        "shipment": {"tracking_number": "123567843932", "show_tracking_map": False},
        "execution_time_ms": 12.0,
    }
    mock_pipeline.return_value = pipeline_result

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(
        db,
        admin,
        "suis le colis 123567843932",
        agent_mode=True,
        ui_language="fr",
    )

    assert result is pipeline_result
    mock_pipeline.assert_called_once()
    mock_chat.assert_not_called()


@patch("app.services.globex_agent.kernel.get_settings")
@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.admin_ollama_chat", return_value="Salut.")
@patch("app.services.globex_agent.kernel.run_admin_client_turn", return_value=None)
def test_kernel_simple_mode_pipeline_none_falls_back_to_ollama(
    mock_pipeline,
    mock_chat,
    _log,
    mock_settings,
):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    settings = MagicMock()
    settings.globex_simple_mode = True
    mock_settings.return_value = settings

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(db, admin, "bonjour", agent_mode=True, ui_language="fr")

    mock_pipeline.assert_called_once()
    mock_chat.assert_called_once()
    assert result["tools_used"] == ["ollama_chat"]


@patch("app.services.globex_agent.kernel.run_admin_client_turn", return_value=None)
@patch("app.services.globex_agent.kernel._humanize_action_with_ollama", side_effect=lambda **kw: (kw.get("local_reply") or "ok", False))
@patch("app.services.globex_agent.kernel.get_settings")
@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.admin_ollama_chat")
@patch("app.services.globex_agent.admin_action_bridge.execute_tool")
@patch("app.services.globex_agent.admin_action_bridge.plan_export_tools")
def test_kernel_simple_mode_export_tracking_pdf(
    mock_plan_export,
    mock_execute,
    mock_chat,
    _log,
    mock_settings,
    _humanize,
    _pipeline,
):
    from app.services.gpt.tool_types import ToolResult
    from app.services.globex_agent.kernel import run_globex_agent_chat

    settings = MagicMock()
    settings.globex_simple_mode = True
    mock_settings.return_value = settings

    mock_plan_export.return_value = [
        ("export_tracking_status_pdf", {"limit": 20, "module": "tracking", "format": "pdf"}),
    ]
    export_spec = {
        "preset": "admin_tracking",
        "filename": "tracking-export.pdf",
        "format": "pdf",
        "export_token": "tok12345678",
    }
    mock_execute.return_value = ToolResult(
        name="export_tracking_pdf",
        success=True,
        data={"export_download": export_spec, "action_executed": True},
    )

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(
        db,
        admin,
        "exporte les colis en pdf",
        agent_mode=True,
        ui_language="fr",
    )

    mock_chat.assert_not_called()
    mock_execute.assert_called_once()
    assert result["export_download"] == export_spec
    assert result["action_executed"] is True


@patch("app.services.globex_agent.kernel.get_settings")
@patch("app.services.globex_agent.kernel.write_log")
@patch("app.services.globex_agent.kernel.admin_ollama_chat", return_value="Salut.")
def test_kernel_simple_mode_bonjour_fallback_ollama(mock_chat, _log, mock_settings):
    from app.services.globex_agent.kernel import run_globex_agent_chat

    settings = MagicMock()
    settings.globex_simple_mode = True
    mock_settings.return_value = settings

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = run_globex_agent_chat(db, admin, "bonjour", agent_mode=True, ui_language="fr")

    mock_chat.assert_called_once()
    assert result["tools_used"] == ["ollama_chat"]
    assert result.get("export_download") is None


@patch("app.services.globex_agent.admin_action_bridge.plan_export_tools")
@patch("app.services.globex_agent.admin_action_bridge.execute_tool")
def test_bridge_rejects_non_whitelisted_tools(mock_execute, mock_plan_export):
    from app.services.globex_agent.admin_action_bridge import try_admin_simple_actions

    mock_plan_export.return_value = [("suspend_user", {"user_id": 2})]

    db = MagicMock()
    admin = MagicMock(id=1, role="admin")

    result = try_admin_simple_actions(
        db,
        admin,
        "suspend user 2",
        agent_mode=True,
        ui_language="fr",
    )

    assert result is None
    mock_execute.assert_not_called()
