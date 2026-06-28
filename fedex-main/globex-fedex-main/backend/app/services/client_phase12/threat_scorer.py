"""Score menace v2 — sans cumul aveugle."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.client_phase12.threat_signatures import scan_threat_signatures
from app.services.prompt_guard_service import RiskLevel, RiskResult


def score_threat(text: str) -> RiskResult:
    settings = get_settings()
    score, reasons, force_block = scan_threat_signatures(text)

    if force_block:
        return RiskResult(score=score, level=RiskLevel.block, reasons=reasons)

    if score >= settings.prompt_guard_block_threshold:
        level = RiskLevel.block
    elif score >= settings.prompt_guard_warn_threshold:
        level = RiskLevel.warn
    else:
        level = RiskLevel.ok

    return RiskResult(score=score, level=level, reasons=reasons)


def is_gray_zone(result: RiskResult) -> bool:
    settings = get_settings()
    if result.level == RiskLevel.block:
        return False
    if result.level == RiskLevel.ok:
        return result.score >= settings.prompt_guard_warn_threshold - 5
    return result.level == RiskLevel.warn
