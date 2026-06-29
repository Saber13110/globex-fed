"""Classification intents journaux d'activité admin."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.logs.logs_followup import (
    extract_focus_log_from_history,
    extract_list_row_index,
    extract_log_ref,
    format_log_ids_hint,
    has_logs_list_data,
    is_logs_followup_message,
    is_logs_history_context,
    is_pronoun_log_reference,
    list_log_ids_from_history,
    resolve_log_id_from_context,
)
from app.services.admin_client.logs.logs_patterns import (
    ANOMALY_RE,
    CONVERSATION_FROM_LOG_RE,
    OPEN_LOG_RE,
    SUSPEND_FROM_LOG_RE,
    is_logs_list_utterance,
    is_user_scoped_logs_message,
)
from app.services.admin_client.logs.logs_service import resolve_user_id_by_email_or_name
from app.services.admin_client.logs.logs_types import LogsPlan, LogsProfile, LogsTaskType
from app.services.admin_client.logs.logs_workspace import is_logs_workspace, score_logs_soft
from app.services.admin_logs_export_service import parse_log_period_hours

_LIST_RE = re.compile(
    r"\b("
    r"liste.{0,35}(logs?|journaux?)|list.{0,35}logs?|"
    r"donne.{0,25}(logs?|journaux?)|montre.{0,25}(logs?|journaux?)|"
    r"journaux?\s+d.?activit[eé]"
    r")\b",
    re.I,
)
_DETAIL_RE = re.compile(
    r"\b(fiche|d[eé]tail|infos?|voir|consulte|ouvr|ouvert).{0,35}(log|journal)\b",
    re.I,
)
_SEARCH_RE = re.compile(
    r"\b(cherche|recherche|search|trouve).{0,40}(logs?|journaux?|dans\s+les\s+logs)\b",
    re.I,
)
_SUMMARY_RE = re.compile(
    r"\b(r[eé]sum[eé]|summary|synth[eè]se|resumer).{0,50}(activit[eé]?|logs?|journaux?|du\s+jour)\b",
    re.I,
)
_LEVEL_RE = re.compile(r"\b(INFO|WARNING|ERROR|DEBUG|critique|danger|alerte)\b", re.I)
_CATEGORY_RE = re.compile(
    r"\b(cat[eé]gorie\s+)?(system|admin|chat|security|s[eé]curit[eé]|auth|user|employee|support)\b",
    re.I,
)
_ACTION_RE = re.compile(r"\baction\s+([a-z][\w.]{2,48})\b", re.I)
_TODAY_RE = re.compile(r"\b(aujourd.?hui|today|du\s+jour|journ[eé]e)\b", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _extract_level_filter(text: str) -> str | None:
    m = _LEVEL_RE.search(text)
    if not m:
        return None
    token = m.group(1).upper()
    if token in {"CRITIQUE", "DANGER", "ALERTE"}:
        return "ERROR"
    if token == "ALERTE":
        return "WARNING"
    return token if token in {"INFO", "WARNING", "ERROR", "DEBUG"} else None


def _extract_category_filter(text: str) -> str | None:
    m = _CATEGORY_RE.search(text)
    if not m:
        return None
    token = (m.group(2) or "").lower()
    if token in {"sécurité", "securite", "security"}:
        return "security"
    return token


def _extract_action_filter(text: str) -> str | None:
    m = _ACTION_RE.search(text)
    return m.group(1) if m else None


def _extract_search_query(message: str) -> str | None:
    text = message or ""
    m = re.search(r'["«]([^"»]{2,200})["»]', text)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(?:contenant|avec|mot)\s+(.{2,80})$", text, re.I)
    if m:
        return m.group(1).strip()
    return None


def _apply_export_flags(plan: LogsPlan, message: str, *, lang: str = "fr") -> LogsPlan:
    from app.services.admin_client.logs.logs_export import (
        export_format_clarify_question,
        has_conflicting_export_formats,
        resolve_logs_export_format,
    )
    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if has_conflicting_export_formats(message):
        plan.needs_clarification = True
        plan.profile = LogsProfile.CLARIFY
        plan.clarification_question = export_format_clarify_question(lang)
        plan.want_pdf = False
        plan.want_excel = False
        return plan

    fmt = resolve_logs_export_format(message)
    if fmt == "xlsx":
        plan.want_excel = True
        plan.want_pdf = False
    elif fmt == "pdf":
        plan.want_pdf = True
        plan.want_excel = False
    elif wants_pdf_format(message):
        plan.want_pdf = True
    return plan


def _build_list_plan(text: str, *, raw: str) -> LogsPlan:
    return LogsPlan(
        task_type=LogsTaskType.log_list,
        profile=LogsProfile.LIST,
        level_filter=_extract_level_filter(text),
        category_filter=_extract_category_filter(text),
        action_filter=_extract_action_filter(text),
        period_hours=parse_log_period_hours(text, default=24),
        since_today=bool(_TODAY_RE.search(text)),
        raw_matches=[raw],
    )


def default_clarify_question(lang: str) -> str:
    if lang == "en":
        return (
            "Would you like to list activity logs, filter by level/user, "
            "view log details, detect anomalies, or summarize a user's day?"
        )
    return (
        "Voulez-vous lister les journaux, filtrer par niveau/utilisateur, "
        "voir le détail d'un log, détecter des anomalies ou résumer l'activité du jour ?"
    )


def default_clarify_plan(lang: str) -> LogsPlan:
    return LogsPlan(
        task_type=LogsTaskType.ambiguous,
        profile=LogsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=default_clarify_question(lang),
        raw_matches=["default_clarify"],
    )


def classify_logs_intent(message: str, *, history_text: str = "", lang: str = "fr") -> LogsPlan:
    if is_user_scoped_logs_message(message):
        return LogsPlan(task_type=LogsTaskType.ambiguous, raw_matches=["user_scoped_defer"])

    text = _normalize(message)
    hist = history_text or ""

    def _finish(plan: LogsPlan) -> LogsPlan:
        return _apply_export_flags(plan, message, lang=lang)

    from app.services.admin_client.logs.logs_export import infer_export_plan_from_message

    direct_export = infer_export_plan_from_message(message, lang=lang)
    if direct_export is not None:
        return direct_export

    if SUSPEND_FROM_LOG_RE.search(text) or (
        re.search(r"\bsuspend", text, re.I)
        and is_logs_history_context(hist)
        and not re.search(r"@", text)
        and (
            is_pronoun_log_reference(message)
            or extract_log_ref(text, history_text=hist) is not None
            or extract_focus_log_from_history(hist) is not None
        )
    ):
        ref = extract_log_ref(text, history_text=hist) or extract_focus_log_from_history(hist)
        return _finish(
            LogsPlan(
                task_type=LogsTaskType.log_suspend_user,
                profile=LogsProfile.CONFIRM,
                log_id=ref,
                raw_matches=["suspend_from_log"],
            )
        )

    if is_logs_followup_message(text, history_text=hist) and not (
        is_logs_list_utterance(message) or _LIST_RE.search(text)
    ):
        if CONVERSATION_FROM_LOG_RE.search(text) or (
            is_pronoun_log_reference(message) and re.search(r"\b(conversation|fil|chat)\b", text, re.I)
        ):
            ref = extract_log_ref(text, history_text=hist) or extract_focus_log_from_history(hist)
            return _finish(
                LogsPlan(
                    task_type=LogsTaskType.log_open_conversation,
                    profile=LogsProfile.CONVERSATION,
                    log_id=ref,
                    raw_matches=["followup_conversation"],
                )
            )
        if ANOMALY_RE.search(text):
            return _finish(
                LogsPlan(
                    task_type=LogsTaskType.log_anomalies,
                    profile=LogsProfile.ANOMALIES,
                    period_hours=parse_log_period_hours(text, default=24),
                    raw_matches=["followup_anomalies"],
                )
            )
        ref = extract_log_ref(text, history_text=hist)
        if ref or is_pronoun_log_reference(text):
            return _finish(
                LogsPlan(
                    task_type=LogsTaskType.log_detail,
                    profile=LogsProfile.DETAIL,
                    log_id=ref or extract_focus_log_from_history(hist),
                    raw_matches=["followup_detail"],
                )
            )
        if extract_list_row_index(text) is not None:
            return _finish(
                LogsPlan(
                    task_type=LogsTaskType.log_detail,
                    profile=LogsProfile.DETAIL,
                    raw_matches=["followup_ordinal"],
                )
            )

    if ANOMALY_RE.search(text):
        return _finish(
            LogsPlan(
                task_type=LogsTaskType.log_anomalies,
                profile=LogsProfile.ANOMALIES,
                level_filter=_extract_level_filter(text),
                period_hours=parse_log_period_hours(text, default=24),
                since_today=bool(_TODAY_RE.search(text)),
                raw_matches=["anomalies"],
            )
        )

    if _SUMMARY_RE.search(text):
        email = _EMAIL_RE.search(message or "")
        if email:
            plan = LogsPlan(
                task_type=LogsTaskType.log_summary_user_day,
                profile=LogsProfile.SUMMARY,
                user_query=email.group(0),
                since_today=True,
                raw_matches=["summary_user_day"],
            )
            return _finish(plan)
        if _TODAY_RE.search(text) or re.search(r"\bdu\s+jour\b", text, re.I):
            plan = LogsPlan(
                task_type=LogsTaskType.log_summary_platform_day,
                profile=LogsProfile.SUMMARY,
                since_today=True,
                raw_matches=["summary_platform_day"],
            )
            return _finish(plan)
        plan = LogsPlan(
            task_type=LogsTaskType.log_summary_user_day,
            profile=LogsProfile.SUMMARY,
            since_today=True,
            needs_clarification=True,
            clarification_question=(
                "Pour quel utilisateur (e-mail) souhaitez-vous le résumé d'activité du jour ?"
                if lang == "fr"
                else "Which user (email) should I summarize for today?"
            ),
            raw_matches=["summary_needs_user"],
        )
        return _finish(plan)

    if OPEN_LOG_RE.search(text) or _DETAIL_RE.search(text):
        ref = extract_log_ref(text, history_text=hist)
        return _finish(
            LogsPlan(
                task_type=LogsTaskType.log_detail,
                profile=LogsProfile.DETAIL,
                log_id=ref,
                raw_matches=["open_log"],
            )
        )

    if CONVERSATION_FROM_LOG_RE.search(text):
        ref = extract_log_ref(text, history_text=hist)
        return _finish(
            LogsPlan(
                task_type=LogsTaskType.log_open_conversation,
                profile=LogsProfile.CONVERSATION,
                log_id=ref,
                raw_matches=["open_conversation"],
            )
        )

    if _DETAIL_RE.search(text) or extract_log_ref(text, history_text=hist):
        return _finish(
            LogsPlan(
                task_type=LogsTaskType.log_detail,
                profile=LogsProfile.DETAIL,
                log_id=extract_log_ref(text, history_text=hist),
                raw_matches=["detail"],
            )
        )

    sq = _extract_search_query(message)
    if _SEARCH_RE.search(text) or sq:
        plan = _build_list_plan(text, raw="search")
        plan.task_type = LogsTaskType.log_search
        plan.search_query = sq or plan.search_query
        return _finish(plan)

    if is_logs_list_utterance(message) or _LIST_RE.search(text):
        return _finish(_build_list_plan(text, raw="list"))

    if is_logs_workspace(text, history_text=hist):
        if score_logs_soft(text) >= 2.5:
            return _finish(_build_list_plan(text, raw="workspace_list"))
        return _finish(default_clarify_plan(lang))

    return _finish(LogsPlan(task_type=LogsTaskType.ambiguous, raw_matches=["no_match"]))


@dataclass
class TargetLogResolution:
    log_id: int | None = None
    user_id: int | None = None
    needs_clarification: bool = False
    clarification_question: str = ""


def _finalize_log_id(
    db: Session,
    ref: int,
    *,
    history_text: str,
    lang: str,
) -> TargetLogResolution:
    resolved = resolve_log_id_from_context(db, ref, history_text=history_text)
    if resolved:
        return TargetLogResolution(log_id=resolved)
    hint = format_log_ids_hint(history_text, lang=lang)
    if lang == "en":
        question = f"Log **#{ref}** not found.{hint}"
    else:
        question = f"Log **#{ref}** introuvable.{hint}"
    return TargetLogResolution(needs_clarification=True, clarification_question=question)


def resolve_target_log(
    db: Session,
    message: str,
    plan: LogsPlan,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> TargetLogResolution:
    if plan.log_id:
        return _finalize_log_id(db, plan.log_id, history_text=history_text, lang=lang)

    text = message or ""
    ref = extract_log_ref(text, history_text=history_text)
    if ref is not None:
        return _finalize_log_id(db, ref, history_text=history_text, lang=lang)

    if has_logs_list_data(history_text):
        idx = extract_list_row_index(text)
        if idx is not None:
            ids = list_log_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return TargetLogResolution(log_id=ids[idx])

    if is_pronoun_log_reference(text) or plan.task_type in {
        LogsTaskType.log_detail,
        LogsTaskType.log_open_conversation,
        LogsTaskType.log_suspend_user,
    }:
        focus = extract_focus_log_from_history(history_text)
        if focus:
            return TargetLogResolution(log_id=focus)

    if plan.task_type in {LogsTaskType.log_detail, LogsTaskType.log_open_conversation, LogsTaskType.log_suspend_user}:
        return TargetLogResolution(
            needs_clarification=True,
            clarification_question=(
                "Quel log ciblez-vous (#id ou numéro dans la liste) ?"
                if lang == "fr"
                else "Which log do you mean (#id or list row number)?"
            ),
        )
    return TargetLogResolution()


def resolve_target_user_for_summary(
    db: Session,
    plan: LogsPlan,
    message: str,
    *,
    lang: str = "fr",
) -> TargetLogResolution:
    if plan.user_id:
        return TargetLogResolution(user_id=plan.user_id)

    q = plan.user_query or ""
    if not q:
        m = _EMAIL_RE.search(message or "")
        if m:
            q = m.group(0)
    if q:
        uid = resolve_user_id_by_email_or_name(db, q)
        if uid:
            return TargetLogResolution(user_id=uid)
        return TargetLogResolution(
            needs_clarification=True,
            clarification_question=(
                f"Aucun utilisateur trouvé pour **{q}**."
                if lang == "fr"
                else f"No user found for **{q}**."
            ),
        )

    return TargetLogResolution(
        needs_clarification=True,
        clarification_question=(
            "Pour quel utilisateur (e-mail ou nom) ?"
            if lang == "fr"
            else "For which user (email or name)?"
        ),
    )
