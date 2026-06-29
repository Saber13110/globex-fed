"""Reformulation LLM grounded — reports admin."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.admin_client.reports.reports_compose import compose_reports_response, reports_source_footer
from app.services.admin_client.reports.reports_types import ReportsPlan
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary

logger = logging.getLogger(__name__)

_META_RE = re.compile(
    r"\b(introduction professionnelle|voici une|voici deux|i am the|je suis le)\b",
    re.I,
)


def _collect_numbers(obj: Any, nums: set[str]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        nums.add(str(int(obj)))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, nums)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, nums)


def _validate_grounded(reply: str, processed: dict[str, Any]) -> bool:
    if not reply or _META_RE.search(reply):
        return False
    allowed: set[str] = set()
    _collect_numbers(processed, allowed)
    for n in re.findall(r"\b\d+\b", reply):
        if n not in allowed and len(n) <= 4:
            return False
    return True


def generate_final_answer_with_llm(
    message: str,
    processed: dict[str, Any],
    plan: ReportsPlan,
    *,
    lang: str,
    share_result: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    deterministic = compose_reports_response(
        processed, plan, lang=lang, share_result=share_result, include_footer=False
    )
    settings = get_settings()
    if not settings.llm_enabled:
        return deterministic + reports_source_footer(lang), None

    facts = json.dumps(
        {
            "runs": processed.get("runs"),
            "run": processed.get("run"),
            "preview_summary": processed.get("preview_summary"),
            "recipients": processed.get("recipients"),
        },
        ensure_ascii=False,
    )[:3500]

    prompt_fr = (
        "Reformule la réponse admin à partir du JSON uniquement. "
        "Ne rajoute aucun chiffre absent du JSON. Pas d'intro. 3-5 phrases max."
    )
    prompt_en = (
        "Rephrase the admin answer from JSON only. "
        "Do not add numbers missing from JSON. No intro. 3-5 sentences max."
    )
    try:
        raw = call_ollama_session_summary(
            f"Données outils:\n{facts}\n\nRéférence:\n{deterministic[:1800]}\n\nQuestion: {message[:300]}",
            session_title="Reports",
            ui_language=lang,
            system_prompt=prompt_fr if lang == "fr" else prompt_en,
        )
        candidate = (raw or "").strip()
        if candidate and candidate != "RESUME_IMPOSSIBLE" and _validate_grounded(candidate, processed):
            return candidate + reports_source_footer(lang), "ollama"
    except LlmProviderError:
        logger.debug("[admin_reports] reformulation indisponible", exc_info=True)
    return deterministic + reports_source_footer(lang), None
