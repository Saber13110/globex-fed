"""Reformulation LLM grounded — jamais source des chiffres."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.admin_client.dashboard.dashboard_answer_engine import format_dashboard_reply
from app.services.admin_client.dashboard.dashboard_types import (
    DashboardPlan,
    DashboardQuestionType,
    DashboardTaskType,
)
from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary

logger = logging.getLogger(__name__)

_META_RE = re.compile(
    r"\b(introduction professionnelle|voici une|voici deux|i am the|je suis le|je suis ravi)\b",
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


def _allowed_numbers(processed: dict[str, Any]) -> set[str]:
    nums: set[str] = set()
    summary = processed.get("summary") or {}
    _collect_numbers(summary, nums)
    _collect_numbers(processed.get("priorities"), nums)
    _collect_numbers(processed.get("activity_digest"), nums)
    return nums


def _validate_grounded(reply: str, processed: dict[str, Any]) -> bool:
    if not reply or _META_RE.search(reply):
        return False
    numbers = re.findall(r"\b\d+\b", reply)
    allowed = _allowed_numbers(processed)
    for n in numbers:
        if n not in allowed and int(n) > 999:
            continue
        if n not in allowed and len(n) <= 3:
            return False
    return True


def generate_final_answer_with_llm(
    message: str,
    snapshot: DashboardSnapshot,
    plan: DashboardPlan,
    *,
    processed_results: dict[str, Any],
) -> tuple[str, str | None]:
    """
    Étape 9 — corps déterministe obligatoire ; LLM reformule uniquement si autorisé.
    Les chiffres viennent toujours des outils, jamais du modèle seul.
    """
    deterministic = format_dashboard_reply(snapshot, plan)
    settings = get_settings()

    if plan.task_type != DashboardTaskType.platform_overview:
        return deterministic, None
    if plan.question_type not in (DashboardQuestionType.EXPLAIN, DashboardQuestionType.SUMMARY):
        return deterministic, None
    if not settings.llm_enabled:
        return deterministic, None

    lang = snapshot.lang
    facts = json.dumps(
        {
            "summary": processed_results.get("summary"),
            "priorities": processed_results.get("priorities"),
            "anomalies": processed_results.get("anomalies"),
            "activity_digest": processed_results.get("activity_digest"),
        },
        ensure_ascii=False,
    )[:4000]

    prompt_fr = (
        "Tu reformules UNIQUEMENT la réponse admin à partir du JSON fourni. "
        "Ne rajoute AUCUN chiffre, AUCUNE donnée absente du JSON. "
        "Pas d'introduction, pas de meta-texte, pas de liste de capacités. "
        "3 à 5 phrases maximum. Garde les valeurs numériques exactement telles quelles."
    )
    prompt_en = (
        "Rephrase the admin answer using ONLY the provided JSON. "
        "Do NOT add any number or fact missing from JSON. "
        "No intro, no meta-text, no capability list. "
        "3 to 5 sentences max. Keep numeric values exactly as given."
    )
    try:
        raw = call_ollama_session_summary(
            f"Données outils (source unique):\n{facts}\n\n"
            f"Réponse déterministe de référence:\n{deterministic[:2000]}\n\n"
            f"Question: {message[:400]}",
            session_title="Dashboard",
            ui_language=lang,
            system_prompt=prompt_fr if lang == "fr" else prompt_en,
        )
        candidate = (raw or "").strip()
        if candidate and candidate != "RESUME_IMPOSSIBLE" and _validate_grounded(candidate, processed_results):
            footer = "\n\n_Source : Dashboard Admin_" if lang == "fr" else "\n\n_Source: Admin Dashboard_"
            return candidate + footer, "ollama"
    except LlmProviderError:
        logger.debug("[admin_dashboard] reformulation LLM indisponible", exc_info=True)

    return deterministic, None


def maybe_dashboard_narrative(
    message: str,
    snapshot: DashboardSnapshot,
    plan: DashboardPlan,
    *,
    deterministic_body: str,
    processed_results: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    """Compat — délègue à generate_final_answer_with_llm."""
    processed = processed_results or {
        "summary": snapshot.summary or {},
        "priorities": (snapshot.summary or {}).get("priorities"),
        "anomalies": (snapshot.summary or {}).get("anomalies"),
        "activity_digest": (snapshot.summary or {}).get("activity_digest"),
    }
    reply, provider = generate_final_answer_with_llm(
        message, snapshot, plan, processed_results=processed
    )
    if reply == deterministic_body or provider is None:
        return deterministic_body if processed_results is None else reply, provider
    return reply, provider
