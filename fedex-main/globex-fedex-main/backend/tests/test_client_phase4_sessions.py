"""Tests Phase 4 — routeur sessions (mocks Ollama, pas d'API live)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.client_phase4 import capabilities
from app.services.client_phase4.router import (
    _deterministic_summarize_plan,
    _fallback_plan_from_message,
    _is_pure_list_request,
    _is_session_workspace_message,
    _looks_like_list_request,
    _looks_like_summarize_request,
    _parse_json_object,
    _plan_from_data,
    _reconcile_sessions_plan,
    _references_past_session,
    _summarize_followup_plan,
    plan_sessions_task,
    try_client_sessions_turn,
)
from app.services.client_phase4.session_executor import (
    deterministic_session_summary,
    execute_list_sessions,
    execute_summarize_session,
)
from app.services.client_phase4.session_reference import (
    enrich_summarize_answers,
    parse_session_reference,
    parse_summarize_selection,
)
from app.services.client_phase4.session_service import build_session_transcript, resolve_session_target
from app.services.client_phase4.session_factual_summary import build_factual_summary_from_transcript
from app.services.client_phase4.session_summary_llm import generate_session_summary
from app.services.client_phase4.session_summary_validator import (
    classify_transcript_content,
    has_sufficient_user_content,
    is_acceptable_summary,
)
from app.services.client_phase4.transcript_filters import is_boilerplate_for_summary


def test_parse_json_object_from_fence():
    raw = '```json\n{"task_type": "list_sessions"}\n```'
    data = _parse_json_object(raw)
    assert data is not None
    assert data["task_type"] == "list_sessions"


def test_plan_from_data_normalizes_task():
    plan = _plan_from_data(
        {
            "task_type": "summarize_session",
            "answers": {"scope": "last"},
            "ready_to_execute": True,
        }
    )
    assert plan["task_type"] == "summarize_session"
    assert plan["answers"]["scope"] == "last"
    assert plan["ready_to_execute"] is True


def test_plan_from_data_invalid_task_becomes_conversation():
    plan = _plan_from_data({"task_type": "hack_everything"})
    assert plan["task_type"] == "conversation"


@patch.object(capabilities, "get_settings")
def test_try_client_sessions_turn_none_when_router_disabled(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=False,
        client_agent_capabilities="chat,fedex,pdf,excel,sessions",
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    assert try_client_sessions_turn(db, user, session, "liste mes chats", 1, "fr") is None


@patch.object(capabilities, "get_settings")
def test_try_client_sessions_turn_none_without_sessions_cap(mock_settings):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="chat,fedex,pdf,excel",
    )
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    assert try_client_sessions_turn(db, user, session, "liste mes chats", 1, "fr") is None


@patch("app.services.client_phase4.router.plan_sessions_task")
@patch.object(capabilities, "get_settings")
def test_try_client_sessions_turn_conversation_returns_none(mock_settings, mock_plan):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="chat,sessions",
    )
    mock_plan.return_value = {"task_type": "conversation", "answers": {}}
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    assert try_client_sessions_turn(db, user, session, "où est mon colis", 1, "fr") is None


@patch("app.services.client_phase4.router.execute_list_sessions")
@patch("app.services.client_phase4.router.plan_sessions_task")
@patch.object(capabilities, "get_settings")
def test_try_client_sessions_turn_list_sessions(mock_settings, mock_plan, mock_exec):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="chat,sessions",
    )
    mock_plan.return_value = {
        "task_type": "list_sessions",
        "assistant_intro": "Bien sûr.",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    mock_exec.return_value = "Vos conversations récentes :\n\n1. Test · 01/01/2026"
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    result = try_client_sessions_turn(db, user, session, "montre mes discussions", 1, "fr")
    assert result is not None
    assert result["intent"] == "list_sessions"
    assert result["source"] == "agent_sessions"
    assert "conversations" in result["reply"].lower()


@patch("app.services.client_phase4.router.plan_sessions_task")
@patch.object(capabilities, "get_settings")
def test_try_client_sessions_turn_clarification(mock_settings, mock_plan):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="sessions",
    )
    mock_plan.return_value = {
        "task_type": "summarize_session",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": False,
        "needs_clarification": True,
        "clarification_question": "Quelle conversation voulez-vous résumer ?",
    }
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    result = try_client_sessions_turn(db, user, session, "résume", 1, "fr")
    assert result is not None
    assert "résumer" in result["reply"].lower()


def test_resolve_session_target_by_hint():
    s1 = SimpleNamespace(
        id=1,
        user_id=1,
        title="Suivi colis FedEx",
        is_pinned=False,
        updated_at=datetime.now(timezone.utc),
    )
    s2 = SimpleNamespace(
        id=2,
        user_id=1,
        title="Export Excel",
        is_pinned=False,
        updated_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    with patch(
        "app.services.client_phase4.session_service.list_user_sessions",
        return_value=[s1, s2],
    ):
        target, ambiguous, err = resolve_session_target(
            db,
            user_id=1,
            current_session_id=99,
            answers={"session_hint": "export"},
        )
    assert err is None
    assert target is not None
    assert target.id == 2
    assert ambiguous == []


def test_resolve_session_target_ambiguous():
    s1 = SimpleNamespace(
        id=1,
        user_id=1,
        title="Colis A",
        is_pinned=True,
        updated_at=datetime.now(timezone.utc),
    )
    s2 = SimpleNamespace(
        id=2,
        user_id=1,
        title="Colis B",
        is_pinned=True,
        updated_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    with patch(
        "app.services.client_phase4.session_service.list_user_sessions",
        return_value=[s1, s2],
    ):
        target, ambiguous, err = resolve_session_target(
            db,
            user_id=1,
            current_session_id=99,
            answers={"scope": "pinned"},
        )
    assert target is None
    assert err == "ambiguous"
    assert len(ambiguous) == 2


@patch("app.services.client_phase4.session_executor.list_user_sessions")
def test_execute_list_sessions_empty(mock_list):
    mock_list.return_value = []
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    reply = execute_list_sessions(db, user, ui_language="fr")
    assert "pas encore" in reply.lower()


def test_is_session_workspace_message_detects_summarize():
    assert _is_session_workspace_message("Résume notre dernière discussion")
    assert not _is_session_workspace_message("Où est mon colis 881135077232")


def test_fallback_plan_list_sessions():
    plan = _fallback_plan_from_message("Montre mes conversations récentes")
    assert plan is not None
    assert plan["task_type"] == "list_sessions"


def test_fallback_plan_summarize_last():
    plan = _fallback_plan_from_message("Résume notre dernière discussion")
    assert plan is not None
    assert plan["task_type"] == "summarize_session"
    assert plan["answers"].get("scope") == "last"


def test_looks_like_list_donne_moi_recents():
    msg = "donne moi les conversations recents"
    assert _looks_like_list_request(msg)
    assert not _looks_like_summarize_request(msg)


def test_looks_like_summarize_with_resume_verb():
    msg = "donne moi resume de cette conversation : 5. Assistance suivi FedEx"
    assert _looks_like_summarize_request(msg)
    assert not _looks_like_list_request(msg)


def test_reconcile_flips_summarize_to_list_for_donne_conversations():
    plan = {
        "task_type": "summarize_session",
        "assistant_intro": "",
        "answers": {"scope": "current"},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    reconciled = _reconcile_sessions_plan("donne moi les conversations recents", plan)
    assert reconciled["task_type"] == "list_sessions"
    assert reconciled["answers"] == {}


def test_fallback_donne_moi_conversations_recents():
    plan = _fallback_plan_from_message("donne moi les conversations recents")
    assert plan is not None
    assert plan["task_type"] == "list_sessions"


@patch("app.services.client_phase4.router.execute_list_sessions")
@patch("app.services.client_phase4.router.call_ollama_agent_plan")
@patch.object(capabilities, "get_settings")
def test_plan_sessions_retry_when_ollama_returns_conversation(
    mock_settings, mock_ollama, mock_exec
):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="sessions",
    )
    mock_ollama.side_effect = [
        '{"task_type": "conversation"}',
        '{"task_type": "list_sessions", "ready_to_execute": true}',
    ]
    mock_exec.return_value = "Vos conversations récentes :\n\n1. A"
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    with patch(
        "app.services.client_phase4.router.build_conversation_history_for_llm",
        return_value="",
    ), patch(
        "app.services.client_phase4.router._session_titles_context",
        return_value="",
    ):
        plan = plan_sessions_task(
            db, user, session, "donne moi les conversations recents", exclude_message_id=1, ui_language="fr"
        )
    assert plan is not None
    assert plan["task_type"] == "list_sessions"
    assert mock_ollama.call_count == 2


@patch("app.services.client_phase4.router.call_ollama_agent_plan")
@patch.object(capabilities, "get_settings")
def test_plan_sessions_offline_fallback_only_on_llm_error(mock_settings, mock_ollama):
    from app.services.llm.providers import LlmProviderError

    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="sessions",
    )
    mock_ollama.side_effect = LlmProviderError("timeout")
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    with patch(
        "app.services.client_phase4.router.build_conversation_history_for_llm",
        return_value="",
    ), patch(
        "app.services.client_phase4.router._session_titles_context",
        return_value="",
    ):
        plan = plan_sessions_task(
            db, user, session, "montre mes discussions récentes", exclude_message_id=1, ui_language="fr"
        )
    assert plan is not None
    assert plan["task_type"] == "list_sessions"


@patch("app.services.client_phase4.router.call_ollama_agent_plan")
@patch.object(capabilities, "get_settings")
def test_plan_sessions_conversation_non_workspace_returns_none(mock_settings, mock_ollama):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="sessions",
    )
    mock_ollama.return_value = '{"task_type": "conversation"}'
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    with patch(
        "app.services.client_phase4.router.build_conversation_history_for_llm",
        return_value="",
    ), patch(
        "app.services.client_phase4.router._session_titles_context",
        return_value="",
    ):
        plan = plan_sessions_task(
            db, user, session, "où est mon colis 881135077232", exclude_message_id=1, ui_language="fr"
        )
    assert plan is None
    assert mock_ollama.call_count == 1


@patch("app.services.client_phase4.router.execute_list_sessions")
@patch("app.services.client_phase4.router.call_ollama_agent_plan")
@patch.object(capabilities, "get_settings")
def test_plan_sessions_task_uses_fallback_on_conversation_json(
    mock_settings, mock_ollama, mock_exec
):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="sessions",
    )
    mock_ollama.side_effect = [
        '{"task_type": "conversation"}',
        '{"task_type": "list_sessions", "ready_to_execute": true}',
    ]
    mock_exec.return_value = "Vos conversations récentes :\n\n1. A"
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    with patch(
        "app.services.client_phase4.router.build_conversation_history_for_llm",
        return_value="",
    ), patch(
        "app.services.client_phase4.router._session_titles_context",
        return_value="",
    ):
        plan = plan_sessions_task(
            db, user, session, "montre mes discussions récentes", exclude_message_id=1, ui_language="fr"
        )
    assert plan is not None
    assert plan["task_type"] == "list_sessions"


def test_parse_session_reference_list_index_and_hint():
    ref = parse_session_reference("résume 5. Assistance suivi FedEx")
    assert ref["list_index"] == 5
    assert "assistance" in (ref["session_hint"] or "")


def test_parse_session_reference_after_colon():
    ref = parse_session_reference(
        "donne moi resume de cette conversation : 5. Assistance suivi FedEx · 27/06/2026 04:14"
    )
    assert ref["list_index"] == 5
    assert "assistance" in (ref["session_hint"] or "")


def test_enrich_summarize_answers_removes_current_when_index():
    answers = enrich_summarize_answers(
        "résume 5. Assistance suivi FedEx",
        {"scope": "current"},
    )
    assert answers.get("list_index") == 5
    assert "scope" not in answers


def test_resolve_session_target_by_list_index():
    sessions = [
        SimpleNamespace(id=i, user_id=1, title=f"S{i}", is_pinned=False, updated_at=datetime.now(timezone.utc))
        for i in range(1, 6)
    ]
    db = MagicMock()
    with patch(
        "app.services.client_phase4.session_service.list_user_sessions",
        return_value=sessions,
    ):
        target, ambiguous, err = resolve_session_target(
            db,
            user_id=1,
            current_session_id=99,
            answers={"list_index": 5},
        )
    assert err is None
    assert target is not None
    assert target.id == 5


def test_resolve_session_target_invalid_index():
    sessions = [
        SimpleNamespace(id=1, user_id=1, title="A", is_pinned=False, updated_at=datetime.now(timezone.utc))
    ]
    db = MagicMock()
    with patch(
        "app.services.client_phase4.session_service.list_user_sessions",
        return_value=sessions,
    ):
        target, ambiguous, err = resolve_session_target(
            db,
            user_id=1,
            current_session_id=99,
            answers={"list_index": 5},
        )
    assert target is None
    assert err == "invalid_index"


def test_build_session_transcript_excludes_bot_list_for_summary():
    list_body = (
        "Vos conversations récentes :\n\n"
        "1. A · 01/01/2026\n2. B · 02/01/2026\n3. C · 03/01/2026"
    )
    rows = [
        SimpleNamespace(
            message_text="Utilisateur: montre mes conversations",
            sender="user",
        ),
        SimpleNamespace(
            message_text=list_body,
            sender="bot",
        ),
        SimpleNamespace(
            message_text="Utilisateur: suivi colis",
            sender="user",
        ),
    ]
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    transcript = build_session_transcript(db, session_id=1, for_summary=True)
    assert "Vos conversations récentes" not in transcript
    assert "montre mes conversations" in transcript


def test_transcript_excludes_pdf_boilerplate_for_summary():
    pdf_body = (
        "Bonjour! Comment puis-je vous aider aujourd'hui?\n"
        "Votre document PDF est prêt — utilisez le lien de téléchargement ci-dessous."
    )
    rows = [
        SimpleNamespace(message_text="Utilisateur: export pdf", sender="user"),
        SimpleNamespace(message_text=pdf_body, sender="bot"),
        SimpleNamespace(message_text="Utilisateur: suivi colis 881135077232", sender="user"),
    ]
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    transcript = build_session_transcript(db, session_id=1, for_summary=True)
    assert "PDF est prêt" not in transcript
    assert "881135077232" in transcript


def test_boilerplate_filter_detects_pdf_and_greeting():
    assert is_boilerplate_for_summary("Votre document PDF est prêt — utilisez le lien de téléchargement ci-dessous.")
    assert is_boilerplate_for_summary("Bonjour! Comment puis-je vous aider aujourd'hui?")
    assert not is_boilerplate_for_summary("Votre colis 881135077232 est en transit à Casablanca.")


def test_validator_rejects_pdf_boilerplate_summary():
    transcript = "Utilisateur: export\nAssistant: ok"
    bad = "Bonjour! Votre document PDF est prêt — utilisez le lien de téléchargement ci-dessous."
    assert not is_acceptable_summary(bad, transcript)


def test_validator_rejects_verbatim_assistant_copy():
    transcript = (
        "Utilisateur: suivi\n"
        "Assistant: Votre colis est en cours de livraison vers Rabat demain matin sans retard."
    )
    copy = "Votre colis est en cours de livraison vers Rabat demain matin sans retard."
    assert not is_acceptable_summary(copy, transcript)


def test_validator_accepts_factual_summary():
    transcript = "Utilisateur: où est mon colis 881135077232\nAssistant: En transit"
    good = (
        "L'utilisateur a demandé le suivi du colis 881135077232. "
        "L'assistant a indiqué que le colis était en transit."
    )
    assert is_acceptable_summary(good, transcript)


def test_validator_rejects_capability_pitch():
    transcript = "Utilisateur: où est mon colis 881135077232\nAssistant: En transit"
    pitch = (
        "Je peux suivre vos colis FedEx en utilisant leur numéro de suivi pour fournir le statut actuel, "
        "la localisation et l'historique des scans. Je peux aussi répondre à vos questions sur nos services "
        "d'expédition et les délais de livraison. Veuillez me donner plus de détails si vous avez besoin d'aide spécifique."
    )
    assert not is_acceptable_summary(pitch, transcript)


def test_validator_requires_transcript_anchor():
    transcript = "Utilisateur: où est mon colis 881135077232 pour Casablanca\nAssistant: En transit"
    generic = (
        "FedEx propose un service de livraison rapide et fiable partout au Maroc avec suivi en temps réel."
    )
    assert not is_acceptable_summary(generic, transcript)


def test_has_sufficient_user_content_requires_min_length():
    short = "Utilisateur: ok\nAssistant: bonjour"
    long_user = (
        "Utilisateur: bonjour je voudrais savoir où est mon colis 881135077232 envoyé depuis Paris vers Casablanca\n"
        "Assistant: votre colis est en transit"
    )
    assert not has_sufficient_user_content(short)
    assert has_sufficient_user_content(long_user)


@patch("app.services.client_phase4.session_summary_llm.call_ollama_session_summary")
def test_generate_session_summary_raises_on_insufficient_transcript(mock_ollama):
    from app.services.llm.providers import LlmProviderError

    with pytest.raises(LlmProviderError, match="summary_insufficient_transcript"):
        generate_session_summary(
            "Utilisateur: ok\nAssistant: bonjour",
            session_title="Test",
            lang="fr",
        )
    mock_ollama.assert_not_called()


@patch("app.services.client_phase4.session_summary_llm.call_ollama_session_summary")
def test_generate_session_summary_honest_on_resume_impossible_token(mock_ollama):
    transcript = (
        "Utilisateur: bonjour je voudrais savoir ou est mon colis 881135077232 envoye depuis Paris vers Casablanca la semaine derniere\n"
        "Assistant: votre colis est en cours de traitement a Casablanca hub principal"
    )
    mock_ollama.return_value = "RESUME_IMPOSSIBLE"
    result = generate_session_summary(transcript, session_title="Test", lang="fr")
    assert "881135077232" in result or "demand" in result.lower()
    assert mock_ollama.call_count == 2


@patch("app.services.client_phase4.session_executor.generate_session_summary")
@patch("app.services.client_phase4.session_executor.build_session_transcript")
@patch("app.services.client_phase4.session_executor.resolve_session_target")
def test_execute_summarize_insufficient_transcript_message(mock_resolve, mock_transcript, mock_gen):
    from app.services.llm.providers import LlmProviderError

    target = SimpleNamespace(id=7, title="Assistance suivi FedEx")
    mock_resolve.return_value = (target, [], None)
    mock_transcript.return_value = "Utilisateur: ok"
    mock_gen.side_effect = LlmProviderError("summary_insufficient_transcript")

    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    reply, needs_clarification = execute_summarize_session(
        db,
        user,
        current_session_id=10,
        answers={"list_index": 14},
        ui_language="fr",
    )
    assert not needs_clarification
    assert "pas assez" in reply.lower() or "échanges" in reply.lower()
    assert "Je peux suivre" not in reply


@patch("app.services.client_phase4.session_summary_llm.call_ollama_session_summary")
def test_generate_session_summary_retries_on_bad_output(mock_ollama):
    transcript = (
        "Utilisateur: bonjour je voudrais un suivi détaillé pour mon colis 881135077232 vers Casablanca\n"
        "Assistant: votre colis est en transit"
    )
    mock_ollama.side_effect = [
        "Bonjour! Votre document PDF est prêt — utilisez le lien de téléchargement ci-dessous.",
        "L'utilisateur a demandé le suivi d'un colis. L'assistant a répondu que le colis était en transit.",
    ]
    result = generate_session_summary(
        transcript,
        session_title="Test",
        lang="fr",
    )
    assert "PDF" not in result
    assert "transit" in result.lower()
    assert mock_ollama.call_count == 2


@patch("app.services.client_phase4.session_executor.generate_session_summary")
@patch("app.services.client_phase4.session_executor.build_session_transcript")
@patch("app.services.client_phase4.session_executor.resolve_session_target")
def test_execute_summarize_shows_honest_message_on_failure(mock_resolve, mock_transcript, mock_gen):
    from app.services.llm.providers import LlmProviderError

    target = SimpleNamespace(id=7, title="Assistance suivi FedEx")
    mock_resolve.return_value = (target, [], None)
    mock_transcript.return_value = "Utilisateur: où est mon colis\nAssistant: En transit"
    mock_gen.side_effect = LlmProviderError("summary_quality")

    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    reply, needs_clarification = execute_summarize_session(
        db,
        user,
        current_session_id=10,
        answers={"list_index": 5},
        ui_language="fr",
    )
    assert not needs_clarification
    assert "surchargé" not in reply.lower()
    assert "PDF" not in reply
    assert "colis" in reply.lower()
    assert "Assistance suivi FedEx" in reply


@patch("app.services.client_phase4.session_executor.generate_session_summary")
@patch("app.services.client_phase4.session_executor.build_session_transcript")
@patch("app.services.client_phase4.session_executor.resolve_session_target")
def test_execute_summarize_ollama_fail_uses_honest_message(mock_resolve, mock_transcript, mock_gen):
    from app.services.llm.providers import LlmProviderError

    target = SimpleNamespace(id=7, title="Assistance suivi FedEx")
    mock_resolve.return_value = (target, [], None)
    mock_transcript.return_value = "Utilisateur: où est mon colis\nAssistant: En transit"
    mock_gen.side_effect = LlmProviderError("timeout")

    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    reply, needs_clarification = execute_summarize_session(
        db,
        user,
        current_session_id=10,
        answers={"list_index": 5},
        ui_language="fr",
    )
    assert not needs_clarification
    assert "surchargé" not in reply.lower()
    assert "automatique" not in reply.lower()
    assert "colis" in reply.lower()
    assert "Assistance suivi FedEx" in reply


@patch("app.services.client_phase4.session_executor.generate_session_summary")
@patch("app.services.client_phase4.session_executor.build_session_transcript")
@patch("app.services.client_phase4.session_executor.resolve_session_target")
def test_execute_summarize_success_returns_ollama_summary(mock_resolve, mock_transcript, mock_gen):
    target = SimpleNamespace(id=7, title="Assistance suivi FedEx")
    mock_resolve.return_value = (target, [], None)
    mock_transcript.return_value = "Utilisateur: où est mon colis\nAssistant: En transit"
    mock_gen.return_value = (
        "L'utilisateur a demandé le suivi d'un colis. L'assistant a indiqué qu'il était en transit."
    )

    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    reply, needs_clarification = execute_summarize_session(
        db,
        user,
        current_session_id=10,
        answers={"list_index": 5},
        ui_language="fr",
    )
    assert not needs_clarification
    assert "transit" in reply.lower()
    assert "Assistance suivi FedEx" in reply


def test_deterministic_session_summary_facts_only():
    text = deterministic_session_summary(
        "Utilisateur: suivi 881135077232\nAssistant: Colis en transit",
        session_title="Test",
        lang="fr",
    )
    assert "881135077232" in text
    assert "automatique" in text.lower()
    assert "Dernière réponse assistant" not in text
    assert "Colis en transit" not in text


def test_parse_session_reference_extracts_datetime():
    ref = parse_session_reference(
        "donne moi resume de cette conversation : 4. liste moi tous les conversations recentes · 27/06/2026 07:01"
    )
    assert ref["list_index"] == 4
    assert ref["session_updated_hint"] is not None
    assert ref["session_updated_hint"].year == 2026
    assert ref["session_updated_hint"].month == 6
    assert ref["session_updated_hint"].day == 27
    assert ref["session_updated_hint"].hour == 7
    assert ref["session_updated_hint"].minute == 1


def test_resolve_session_target_prefers_date_match():
    wrong_date = datetime(2026, 6, 27, 6, 0, tzinfo=timezone.utc)
    right_date = datetime(2026, 6, 27, 7, 1, tzinfo=timezone.utc)
    sessions = [
        SimpleNamespace(
            id=1,
            user_id=1,
            title="liste moi tous les conversations recentes",
            is_pinned=False,
            updated_at=wrong_date,
        ),
        SimpleNamespace(
            id=2,
            user_id=1,
            title="liste moi tous les conversations recentes",
            is_pinned=False,
            updated_at=right_date,
        ),
        SimpleNamespace(
            id=3,
            user_id=1,
            title="Autre",
            is_pinned=False,
            updated_at=datetime.now(timezone.utc),
        ),
        SimpleNamespace(
            id=4,
            user_id=1,
            title="Encore",
            is_pinned=False,
            updated_at=datetime.now(timezone.utc),
        ),
    ]
    db = MagicMock()
    with patch(
        "app.services.client_phase4.session_service.list_user_sessions",
        return_value=sessions,
    ):
        target, ambiguous, err = resolve_session_target(
            db,
            user_id=1,
            current_session_id=99,
            answers={
                "list_index": 4,
                "session_hint": "liste moi tous les conversations recentes",
                "session_updated_hint": right_date,
            },
        )
    assert err is None
    assert target is not None
    assert target.id == 2


def test_validator_rejects_meta_refusal():
    transcript = "Utilisateur: montre mes conversations recentes\nAssistant: ok"
    refusal = (
        "Je ne peux pas accéder aux conversations précédentes. "
        "Pouvez-vous me dire ce qui se passe dans cette conversation ?"
    )
    assert not is_acceptable_summary(refusal, transcript)


def test_validator_rejects_title_echo_only():
    transcript = "Utilisateur: liste moi tous les conversations recentes\nAssistant: ok"
    echo = "liste moi tous les conversations recentes"
    assert not is_acceptable_summary(echo, transcript, session_title="liste moi tous les conversations recentes")


def test_classify_short_transcript_session_4():
    transcript = "Utilisateur: liste moi tous les conversations recentes"
    assert classify_transcript_content(transcript) == "short"


def test_factual_summary_full_tier_narrative_lines():
    transcript = (
        "Utilisateur: salut\n"
        "Assistant: bonjour\n"
        "Utilisateur: tu peux m'aider avec mon colis 456092427388\n"
        "Assistant: bien sûr\n"
        "Utilisateur: et aussi celui 880892017122\n"
        "Assistant: ok"
    )
    result = build_factual_summary_from_transcript(
        transcript,
        session_title="Assistance suivi FedEx",
        lang="fr",
        tier="full",
    )
    lines = [ln for ln in result.splitlines() if ln.strip()]
    assert len(lines) >= 4
    assert "456092427388" in result
    assert "880892017122" in result
    assert "Sujets abordés :" not in result
    assert "L'utilisateur" in result


def test_factual_summary_short_tier_unchanged():
    transcript = (
        "Utilisateur: salut\n"
        "Utilisateur: tu peux m'aider avec mon colis 456092427388\n"
        "Utilisateur: et aussi celui 880892017122\n"
    )
    result = build_factual_summary_from_transcript(
        transcript,
        session_title="Assistance suivi FedEx",
        lang="fr",
        tier="short",
    )
    assert "Sujets abordés :" in result
    assert "Numéros de suivi mentionnés :" in result
    assert result.count("\n") <= 1


@patch("app.services.client_phase4.session_summary_llm.call_ollama_session_summary")
def test_generate_session_summary_short_returns_factual(mock_ollama):
    mock_ollama.return_value = "Je ne peux pas accéder aux conversations précédentes."
    transcript = "Utilisateur: liste moi tous les conversations recentes"
    result = generate_session_summary(
        transcript,
        session_title="liste moi tous les conversations recentes",
        lang="fr",
    )
    assert "conversations" in result.lower() or "liste" in result.lower()
    assert "accéder" not in result.lower()


@patch("app.services.client_phase4.session_summary_llm.call_ollama_session_summary")
def test_generate_session_summary_full_falls_back_to_factual_on_quality_fail(mock_ollama):
    transcript = (
        "Utilisateur: bonjour je voudrais savoir où est mon colis 881135077232 envoyé depuis Paris vers Casablanca la semaine dernière\n"
        "Assistant: votre colis est en transit vers le hub principal"
    )
    mock_ollama.side_effect = [
        "FedEx propose un service de livraison rapide partout au Maroc.",
        "FedEx propose un service de livraison rapide partout au Maroc.",
    ]
    result = generate_session_summary(transcript, session_title="Assistance suivi FedEx", lang="fr")
    assert "881135077232" in result
    assert "L'utilisateur" in result
    assert "Sujets abordés :" not in result
    assert mock_ollama.call_count == 2


def test_parse_title_dot_date_extracts_hint_and_datetime():
    ref = parse_session_reference("liste moi tous les conversations recentes · 27/06/2026 07:01")
    assert ref["session_hint"] == "liste moi tous les conversations recentes"
    assert ref["session_updated_hint"] is not None
    assert ref["session_updated_hint"].hour == 7


def test_parse_ordinal_la_5eme():
    assert parse_summarize_selection("la 5eme") == 5
    ref = parse_session_reference("la 5eme")
    assert ref["list_index"] == 5


def test_is_pure_list_false_when_date_in_title():
    msg = "liste moi tous les conversations recentes · 27/06/2026 07:01"
    assert _references_past_session(msg)
    assert not _is_pure_list_request(msg)


def test_reconcile_keeps_summarize_when_title_has_list_word_and_date():
    plan = {
        "task_type": "summarize_session",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    msg = "liste moi tous les conversations recentes · 27/06/2026 07:01"
    reconciled = _reconcile_sessions_plan(msg, plan)
    assert reconciled["task_type"] == "summarize_session"
    assert reconciled["answers"].get("session_hint")


def test_reconcile_upgrades_list_to_summarize_on_title_date():
    plan = {
        "task_type": "list_sessions",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    msg = "liste moi tous les conversations recentes · 27/06/2026 07:01"
    reconciled = _reconcile_sessions_plan(msg, plan)
    assert reconciled["task_type"] == "summarize_session"
    assert reconciled["answers"].get("session_updated_hint") is not None


def test_parse_assistance_fedex_date_de_quoi():
    msg = (
        "Assistance suivi FedEx · 27/06/2026 06:14 depuis le titre "
        "et la date que je fournis, trouve la conversation et dis-moi de quoi elle parle"
    )
    ref = parse_session_reference(msg)
    assert "assistance" in (ref["session_hint"] or "")
    assert ref["session_updated_hint"] is not None
    assert ref["session_updated_hint"].hour == 6
    assert _looks_like_summarize_request(msg)


@patch("app.services.client_phase4.router._last_bot_message_text")
def test_summarize_followup_la_5eme_after_ambiguous(mock_last_bot):
    mock_last_bot.return_value = (
        "Plusieurs conversations correspondent. Laquelle souhaitez-vous résumer ?\n"
        "1. Colis A · 27/06/2026 06:00\n"
        "2. Colis B · 27/06/2026 06:10\n"
        "3. Colis C · 27/06/2026 06:12\n"
        "4. Colis D · 27/06/2026 06:13\n"
        "5. liste moi tous les conversations recentes · 27/06/2026 07:01"
    )
    db = MagicMock()
    plan = _summarize_followup_plan(db, session_id=10, message="la 5eme")
    assert plan is not None
    assert plan["task_type"] == "summarize_session"
    assert plan["answers"].get("session_hint") == "liste moi tous les conversations recentes"
    assert plan["answers"].get("session_updated_hint") is not None


def test_parse_title_dot_time_only():
    ref = parse_session_reference("Assistance suivi FedEx · 06:14 de quoi elle parle")
    assert ref["session_hint"] == "assistance suivi fedex"
    assert ref["session_time_hint"] == (6, 14)
    assert ref["session_updated_hint"] is None


def test_workspace_true_for_de_quoi_elle_parle():
    msg = "Assistance suivi FedEx · 06:14 de quoi elle parle"
    assert _is_session_workspace_message(msg)
    assert _looks_like_summarize_request(msg)


def test_references_past_session_with_time_only():
    msg = "Assistance suivi FedEx · 06:14 de quoi elle parle"
    assert _references_past_session(msg)


def test_resolve_session_target_by_hint_and_time():
    early = datetime(2026, 6, 27, 4, 14, tzinfo=timezone.utc)
    late = datetime(2026, 6, 27, 6, 14, tzinfo=timezone.utc)
    sessions = [
        SimpleNamespace(
            id=1,
            user_id=1,
            title="Assistance suivi FedEx",
            is_pinned=False,
            updated_at=early,
        ),
        SimpleNamespace(
            id=2,
            user_id=1,
            title="Assistance suivi FedEx",
            is_pinned=False,
            updated_at=late,
        ),
    ]
    db = MagicMock()
    with patch(
        "app.services.client_phase4.session_service.list_user_sessions",
        return_value=sessions,
    ):
        target, ambiguous, err = resolve_session_target(
            db,
            user_id=1,
            current_session_id=99,
            answers={
                "session_hint": "assistance suivi fedex",
                "session_time_hint": (6, 14),
            },
        )
    assert err is None
    assert target is not None
    assert target.id == 2


def test_deterministic_summarize_plan_on_short_format():
    msg = "Assistance suivi FedEx · 06:14 de quoi elle parle"
    plan = _deterministic_summarize_plan(msg)
    assert plan is not None
    assert plan["task_type"] == "summarize_session"
    assert plan["answers"].get("session_hint") == "assistance suivi fedex"
    assert plan["answers"].get("session_time_hint") == (6, 14)


@patch("app.services.client_phase4.router._session_titles_context", return_value="")
@patch("app.services.client_phase4.router.build_conversation_history_for_llm", return_value="")
@patch("app.services.client_phase4.router.call_ollama_agent_plan")
@patch.object(capabilities, "get_settings")
def test_plan_sessions_task_bypass_when_ollama_conversation(
    mock_settings, mock_ollama, _mock_history, _mock_titles
):
    mock_settings.return_value = SimpleNamespace(
        client_agent_router_enabled=True,
        client_agent_capabilities="sessions",
    )
    mock_ollama.return_value = '{"task_type": "conversation"}'
    db = MagicMock()
    user = SimpleNamespace(id=1, preferred_language="fr")
    session = SimpleNamespace(id=10, user_id=1)
    msg = "Assistance suivi FedEx · 06:14 de quoi elle parle"
    plan = plan_sessions_task(
        db, user, session, msg, exclude_message_id=1, ui_language="fr"
    )
    assert plan is not None
    assert plan["task_type"] == "summarize_session"
    assert plan["answers"].get("session_time_hint") == (6, 14)
