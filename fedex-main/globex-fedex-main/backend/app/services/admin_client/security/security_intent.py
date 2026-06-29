"""Classification intents Security IDS admin."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.admin_client.security.security_followup import (
    extract_focus_incident_from_history,
    extract_incident_ref,
    extract_list_row_index,
    format_incident_ids_hint,
    has_incidents_list_data,
    is_security_followup_message,
    is_security_history_context,
    resolve_incident_id_from_context,
)
from app.services.admin_client.security.security_patterns import (
    DETAIL_RE,
    REPORT_RE,
    SCAN_RE,
    SECURITY_LIST_UTTERANCE_RE,
    SUMMARY_RE,
    is_logs_anomaly_scope,
    is_security_list_utterance,
)
from app.services.admin_client.security.security_types import SecurityPlan, SecurityProfile, SecurityTaskType
from app.services.admin_client.security.security_workspace import is_security_workspace, score_security_soft

_STATUS_OPEN_RE = re.compile(
    r"\b(ouverts?|open|actifs?|active|en\s+cours|pending)\b",
    re.I,
)
_STATUS_RESOLVED_RE = re.compile(
    r"\b(r[eé]solus?|resolved|ferm[eé]s?|closed|trait[eé]s?)\b",
    re.I,
)
_STATUS_FP_RE = re.compile(
    r"\b(faux\s+positif|false\s+positive|fp)\b",
    re.I,
)
_SEVERITY_RE = re.compile(r"\b(critical|critique|high|[eé]lev[eé]|medium|moyen|low|faible)\b", re.I)
_AI_SCAN_RE = re.compile(r"\b(ia|ai|gemini|intelligence)\b", re.I)


def _apply_pdf_flag(plan: SecurityPlan, message: str) -> SecurityPlan:
    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if wants_pdf_format(message):
        plan.want_pdf = True
    return plan


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _extract_status_filter(text: str) -> str | None:
    if _STATUS_FP_RE.search(text):
        return "false_positive"
    if _STATUS_RESOLVED_RE.search(text):
        return "resolved"
    if _STATUS_OPEN_RE.search(text):
        return "active"
    if re.search(r"\b(tous|all)\b", text, re.I):
        return "all"
    return None


def _extract_severity_filter(text: str) -> str | None:
    m = _SEVERITY_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token in {"critique", "critical"}:
        return "critical"
    if token in {"élevé", "eleve", "high"}:
        return "high"
    if token in {"moyen", "medium"}:
        return "medium"
    if token in {"faible", "low"}:
        return "low"
    return token


def _build_list_plan(text: str, *, raw: str) -> SecurityPlan:
    return SecurityPlan(
        task_type=SecurityTaskType.security_incident_list,
        profile=SecurityProfile.LIST,
        status_filter=_extract_status_filter(text),
        severity_filter=_extract_severity_filter(text),
        raw_matches=[raw],
    )


def default_clarify_question(lang: str) -> str:
    if lang == "en":
        return (
            "Would you like to list security incidents, run an IDS scan, "
            "view incident details, summarize open incidents, or generate a security report?"
        )
    return (
        "Voulez-vous lister les incidents sécurité, lancer un scan IDS, "
        "voir le détail d'un incident, résumer les incidents ouverts ou générer un rapport sécurité ?"
    )


def default_clarify_plan(lang: str) -> SecurityPlan:
    return SecurityPlan(
        task_type=SecurityTaskType.ambiguous,
        profile=SecurityProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=default_clarify_question(lang),
        raw_matches=["default_clarify"],
    )


def classify_security_intent(
    message: str,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> SecurityPlan:
    if is_logs_anomaly_scope(message):
        return SecurityPlan(task_type=SecurityTaskType.ambiguous, raw_matches=["logs_anomaly_defer"])

    text = _normalize(message)
    hist = history_text or ""

    def _finish(plan: SecurityPlan) -> SecurityPlan:
        return _apply_pdf_flag(plan, message)

    if SCAN_RE.search(text):
        return _finish(
            SecurityPlan(
                task_type=SecurityTaskType.security_scan,
                profile=SecurityProfile.SCAN,
                include_ai_scan=bool(_AI_SCAN_RE.search(message or "")),
                raw_matches=["scan"],
            )
        )

    if is_security_followup_message(text, history_text=hist) and not (
        is_security_list_utterance(message) or SECURITY_LIST_UTTERANCE_RE.search(text)
    ):
        ref = extract_incident_ref(text, history_text=hist)
        if ref or extract_list_row_index(text) is not None:
            return _finish(
                SecurityPlan(
                    task_type=SecurityTaskType.security_incident_detail,
                    profile=SecurityProfile.DETAIL,
                    incident_id=ref or extract_focus_incident_from_history(hist),
                    raw_matches=["followup_detail"],
                )
            )
        if SUMMARY_RE.search(text) or re.search(r"\b(r[eé]sum[eé]|resume)\b", text, re.I):
            return _finish(
                SecurityPlan(
                    task_type=SecurityTaskType.security_incident_summary,
                    profile=SecurityProfile.SUMMARY,
                    raw_matches=["followup_summary"],
                )
            )
        if REPORT_RE.search(text):
            return _finish(
                SecurityPlan(
                    task_type=SecurityTaskType.security_report,
                    profile=SecurityProfile.REPORT,
                    raw_matches=["followup_report"],
                )
            )

    if SUMMARY_RE.search(text) or re.search(
        r"\b(r[eé]sum[eé]|resume).{0,40}incident", text, re.I
    ):
        return _finish(
            SecurityPlan(
                task_type=SecurityTaskType.security_incident_summary,
                profile=SecurityProfile.SUMMARY,
                raw_matches=["summary"],
            )
        )

    if REPORT_RE.search(text):
        return _finish(
            SecurityPlan(
                task_type=SecurityTaskType.security_report,
                profile=SecurityProfile.REPORT,
                raw_matches=["report"],
            )
        )

    if DETAIL_RE.search(text) or extract_incident_ref(text, history_text=hist):
        return _finish(
            SecurityPlan(
                task_type=SecurityTaskType.security_incident_detail,
                profile=SecurityProfile.DETAIL,
                incident_id=extract_incident_ref(text, history_text=hist),
                raw_matches=["detail"],
            )
        )

    if is_security_list_utterance(message) or SECURITY_LIST_UTTERANCE_RE.search(text):
        return _finish(_build_list_plan(text, raw="list"))

    if is_security_workspace(text, history_text=hist):
        if score_security_soft(text) >= 2.5:
            return _finish(_build_list_plan(text, raw="workspace_list"))
        return _finish(default_clarify_plan(lang))

    return _finish(SecurityPlan(task_type=SecurityTaskType.ambiguous, raw_matches=["no_match"]))


@dataclass
class TargetIncidentResolution:
    incident_id: int | None = None
    needs_clarification: bool = False
    clarification_question: str = ""


def _finalize_incident_id(
    db: Session,
    ref: int,
    *,
    history_text: str,
    lang: str,
) -> TargetIncidentResolution:
    resolved = resolve_incident_id_from_context(db, ref, history_text=history_text)
    if resolved:
        return TargetIncidentResolution(incident_id=resolved)
    hint = format_incident_ids_hint(history_text, lang=lang)
    if lang == "en":
        question = f"Security incident **#{ref}** not found.{hint}"
    else:
        question = f"Incident sécurité **#{ref}** introuvable.{hint}"
    return TargetIncidentResolution(needs_clarification=True, clarification_question=question)


def resolve_target_incident(
    db: Session,
    message: str,
    plan: SecurityPlan,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> TargetIncidentResolution:
    if plan.incident_id:
        return _finalize_incident_id(db, plan.incident_id, history_text=history_text, lang=lang)

    ref = extract_incident_ref(message or "", history_text=history_text)
    if ref is not None:
        return _finalize_incident_id(db, ref, history_text=history_text, lang=lang)

    if has_incidents_list_data(history_text):
        idx = extract_list_row_index(message or "")
        if idx is not None:
            from app.services.admin_client.security.security_followup import list_incident_ids_from_history

            ids = list_incident_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return TargetIncidentResolution(incident_id=ids[idx])

    if plan.task_type == SecurityTaskType.security_incident_detail:
        return TargetIncidentResolution(
            needs_clarification=True,
            clarification_question=(
                "Quel incident ciblez-vous (#id ou numéro dans la liste) ?"
                if lang == "fr"
                else "Which security incident do you mean (#id or list row)?"
            ),
        )
    return TargetIncidentResolution()
