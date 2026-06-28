"""Point d'entrée Phase 12 — évaluation menace."""

from __future__ import annotations

from app.services.client_phase12.business_intent import detect_business_intent
from app.services.client_phase12.threat_adjudicator import adjudicate_gray_zone
from app.services.client_phase12.threat_scorer import is_gray_zone, score_threat
from app.services.gpt.memory_service import detect_language_preference
from app.services.prompt_guard_service import RiskLevel, RiskResult


def assess_message_threat(text: str, *, ui_language: str | None = None) -> RiskResult:
    if detect_language_preference(text):
        return RiskResult(score=0, level=RiskLevel.ok, reasons=["language_preference"])

    biz = detect_business_intent(text)
    if biz:
        return RiskResult(score=0, level=RiskLevel.ok, reasons=[f"business_intent:{biz}"])

    scored = score_threat(text)
    if scored.level == RiskLevel.block:
        return scored

    if is_gray_zone(scored):
        return adjudicate_gray_zone(text, scored, ui_language=ui_language)

    return scored
