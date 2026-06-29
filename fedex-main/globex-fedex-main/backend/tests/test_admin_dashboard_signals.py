"""Tests scoring dashboard signals."""

from __future__ import annotations

from app.services.admin_client.dashboard.dashboard_signals import (
    pick_top_signal,
    score_dashboard_signals,
    signal_to_task_type,
)


def test_score_activity_resume_paraphrase():
    scores = score_dashboard_signals("Donne-moi un resume rapide de l activite recente")
    assert scores["activity"] >= 2.0
    top, _, _ = pick_top_signal(scores)
    assert top == "activity"


def test_score_health_problem():
    scores = score_dashboard_signals("Est-ce que la plateforme a un probleme aujourd hui")
    assert scores["health"] >= 2.0


def test_score_kpi_advisory():
    scores = score_dashboard_signals("Quels chiffres importants dois-je regarder en priorite")
    assert scores["kpi_advisory"] >= 2.0


def test_signal_to_task_activity():
    assert signal_to_task_type("activity") == "recent_activity"
