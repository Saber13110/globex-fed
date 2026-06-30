"""Classification intents Mission Control admin."""

from __future__ import annotations

import re

from app.services.admin_client.missions.missions_followup import (
    extract_mission_ref,
    wants_last_failed_mission,
)
from app.services.admin_client.missions.missions_types import (
    MissionsPlan,
    MissionsProfile,
    MissionsTaskType,
)
from app.services.admin_client.missions.missions_workspace import is_missions_workspace

_LIST_RE = re.compile(
    r"\b("
    r"liste\s+moi\s+(les\s+)?missions?|"
    r"liste.{0,35}missions?|list.{0,35}missions?|"
    r"lister\s+(les\s+)?missions?|"
    r"missions?\s+agents?|agents?\s+missions?|"
    r"missions?\s+(en\s+cours|running|echou\w*|"
    r"[eé]chou\w*|failed|fail(?:ed|ure)?|termin[eé]\w*|completed|"
    r"annul[eé]\w*|cancelled|brouillon|draft|planifi[eé]\w*|scheduled)|"
    r"mission.{0,18}echou\w*|missions?.{0,18}echou\w*|"
    r"montre.{0,25}missions?|affiche.{0,25}missions?|"
    r"donne.{0,25}missions?"
    r")\b",
    re.I,
)
_RESULTS_RE = re.compile(
    r"\b(r[eé]sultats?|outputs?|r[eé]sultat\s+final)\b.{0,35}\bmission\b",
    re.I,
)
_RESULTS_ALT_RE = re.compile(
    r"\bmission\b.{0,35}\b(r[eé]sultats?|outputs?)\b",
    re.I,
)
_LOGS_RE = re.compile(
    r"\b("
    r"logs?\s+(de\s+la\s+)?mission|journal\s+(d['']?)?ex[eé]cution|"
    r"r[eé]sum[eé]|synth[eè]se|analyse"
    r")\b.{0,40}\bmission\b",
    re.I,
)
_LOGS_ALT_RE = re.compile(
    r"\bmission\b.{0,40}\b(logs?|journal|r[eé]sum[eé]|synth[eè]se)\b",
    re.I,
)
_RETRY_RE = re.compile(
    r"\b(relancer|r[eé]essayer|retry|relance)\b.{0,35}\bmission\b",
    re.I,
)
_RESUME_RE = re.compile(
    r"\b(reprendre|resume|reprise)\b.{0,35}\bmission\b",
    re.I,
)
_CANCEL_RE = re.compile(
    r"\b(annuler|cancel|stop(?:per)?|arr[eê]ter)\b.{0,35}\bmission\b",
    re.I,
)
_DELETE_RE = re.compile(
    r"\b(supprimer|delete|effacer|retirer)\b.{0,35}\bmission\b",
    re.I,
)

_STATUS_MAP = {
    "failed": ("échou", "echou", "failed", "echec", "échec", "fail"),
    "running": ("en cours", "running", "cours"),
    "completed": ("termin", "completed", "fini"),
    "cancelled": ("annul", "cancelled"),
    "draft": ("brouillon", "draft"),
    "paused": ("pause", "paused"),
    "scheduled": ("planifi", "scheduled"),
}

_PROFILE_FOR_TASK = {
    MissionsTaskType.mission_list: MissionsProfile.LIST,
    MissionsTaskType.mission_results: MissionsProfile.RESULTS,
    MissionsTaskType.mission_logs_summary: MissionsProfile.LOGS,
    MissionsTaskType.mission_retry: MissionsProfile.DONE,
    MissionsTaskType.mission_resume: MissionsProfile.DONE,
    MissionsTaskType.mission_cancel: MissionsProfile.CONFIRM,
    MissionsTaskType.mission_delete: MissionsProfile.CONFIRM_DELETE,
}


def _extract_status_filter(message: str) -> str | None:
    text = (message or "").lower()
    if re.search(r"\bechou\w*\b", text) or re.search(r"\béchou", text):
        return "failed"
    for status, tokens in _STATUS_MAP.items():
        for tok in tokens:
            if tok in text:
                return status
    return None


def default_clarify_plan(lang: str) -> MissionsPlan:
    q = (
        "Que souhaitez-vous faire sur les missions agent ? "
        "(lister, résultats, logs, relancer, annuler, supprimer — ex. « mission #521 »)"
        if lang == "fr"
        else "What would you like to do with agent missions? "
        "(list, results, logs, retry, cancel, delete — e.g. « mission #521 »)"
    )
    return MissionsPlan(
        task_type=MissionsTaskType.ambiguous,
        profile=MissionsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=q,
    )


def classify_missions_intent(
    message: str,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> MissionsPlan:
    text = (message or "").strip()
    hist = history_text or ""

    if _DELETE_RE.search(text):
        task = MissionsTaskType.mission_delete
    elif _CANCEL_RE.search(text):
        task = MissionsTaskType.mission_cancel
    elif _RESUME_RE.search(text):
        task = MissionsTaskType.mission_resume
    elif _RETRY_RE.search(text):
        task = MissionsTaskType.mission_retry
    elif _LOGS_RE.search(text) or _LOGS_ALT_RE.search(text):
        task = MissionsTaskType.mission_logs_summary
    elif _RESULTS_RE.search(text) or _RESULTS_ALT_RE.search(text):
        task = MissionsTaskType.mission_results
    elif _LIST_RE.search(text) or wants_last_failed_mission(text):
        task = MissionsTaskType.mission_list
    elif is_missions_workspace(text, history_text=hist):
        mid = extract_mission_ref(text, history_text=hist)
        if mid is not None:
            if re.search(r"\b(logs?|journal|r[eé]sum[eé])\b", text, re.I):
                task = MissionsTaskType.mission_logs_summary
            elif re.search(r"\b(r[eé]sultats?)\b", text, re.I):
                task = MissionsTaskType.mission_results
            else:
                task = MissionsTaskType.mission_results
        else:
            task = MissionsTaskType.mission_list
    else:
        return MissionsPlan(task_type=MissionsTaskType.ambiguous)

    profile = _PROFILE_FOR_TASK.get(task, MissionsProfile.LIST)
    status_filter = _extract_status_filter(text)
    if wants_last_failed_mission(text):
        status_filter = "failed"

    mission_id = extract_mission_ref(text, history_text=hist)
    needs_id = task in {
        MissionsTaskType.mission_results,
        MissionsTaskType.mission_logs_summary,
        MissionsTaskType.mission_retry,
        MissionsTaskType.mission_resume,
        MissionsTaskType.mission_cancel,
        MissionsTaskType.mission_delete,
    }

    plan = MissionsPlan(
        task_type=task,
        mission_id=mission_id,
        status_filter=status_filter,
        profile=profile,
    )

    if needs_id and mission_id is None and not wants_last_failed_mission(text):
        plan.needs_clarification = True
        plan.profile = MissionsProfile.CLARIFY
        plan.clarification_question = (
            "Quelle mission ciblez-vous ? Indiquez « mission #id » ou le numéro dans la liste."
            if lang == "fr"
            else "Which mission do you mean? Use « mission #id » or the list row number."
        )

    return plan
