"""Classification intents tickets support admin — phase 1 lecture."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket
from app.services.admin_client.tickets.tickets_entity_memory import (
    is_pronoun_ticket_reference,
    resolve_pronoun_or_context,
)
from app.services.admin_client.tickets.tickets_followup import (
    extract_email_from_message,
    extract_list_row_index,
    extract_ticket_number_token,
    extract_ticket_ref,
    format_ticket_ids_hint,
    is_tickets_followup_message,
    has_tickets_list_data,
    is_tickets_history_context,
    list_ticket_ids_from_history,
    resolve_ticket_id_from_context,
)
from app.services.admin_client.tickets.tickets_patterns import is_tickets_list_utterance
from app.services.admin_client.tickets.tickets_types import TicketsPlan, TicketsProfile, TicketsTaskType
from app.services.admin_client.tickets.tickets_workspace import (
    is_tickets_workspace,
    normalize_tickets_text,
    score_tickets_soft,
)

_LIST_RE = re.compile(
    r"\b("
    r"liste.{0,35}tickets?|list.{0,35}tickets?|"
    r"(tous les|all)\s+(les\s+)?tickets?|"
    r"tickets?\s+(ouverts?|open|pending|en\s+cours|r[eé]solus?|resolved|closed|ferm[eé]s?)|"
    r"montre.{0,25}tickets?|affiche.{0,25}tickets?|"
    r"donne.{0,25}tickets?"
    r")\b",
    re.I,
)
_DETAIL_RE = re.compile(
    r"\b(fiche|d[eé]tail|infos?|voir|consulte).{0,35}ticket\b",
    re.I,
)
_DETAILS_PLURAL_RE = re.compile(
    r"\b(d[eé]tails?|fiches?|infos?).{0,40}\btickets\b",
    re.I,
)
_CLIENT_TICKETS_RE = re.compile(
    r"\btickets?\s+(du|de|pour)\s+",
    re.I,
)
_SUMMARY_RE = re.compile(
    r"\b(r[eé]sum[eé]|summary|synth[eè]se).{0,35}tickets?\b",
    re.I,
)
_WRITE_REPLY_RE = re.compile(
    r"\b(r[eé]?ponds?|repond(?:re|s)?|reply|envo(?:ie|ye|yer)|message\s+au)\b",
    re.I,
)
_WRITE_RESOLVE_RE = re.compile(
    r"\b(r[eé]solu|resolu|resolve|marqu(?:er|e)\s+comme)\b",
    re.I,
)
_WRITE_CLOSE_RE = re.compile(
    r"\b(ferm(?:er|e)|close|closed)\b",
    re.I,
)
_DRAFT_RE = re.compile(
    r"\b(brouillon|draft|r[eé]dig(?:e|er)|propose|sugg[eè]re)\b",
    re.I,
)
_REPLY_BODY_PATTERNS = (
    re.compile(r"(?:avec(?:\s+le\s+message)?|en\s+disant|message)\s*[:«\"]([^»\"]{3,3000})", re.I),
    re.compile(r"«([^»]{3,3000})»"),
    re.compile(r'"([^"]{3,3000})"'),
    re.compile(r"(?:réponds?|repond)\b[^:]{0,40}:\s*(.+)$", re.I | re.MULTILINE),
)

_STATUS_RE = re.compile(
    r"\b(ouverts?|open|pending|en\s+cours|"
    r"r[eé]solus?|resolved|ferm[eé]s?|closed|tous|all)\b",
    re.I,
)
_PRIORITY_RE = re.compile(r"\b(priorit[eé]\s+)?(low|basse|medium|moyenne|high|haute|urgent)\b", re.I)
_CATEGORY_RE = re.compile(
    r"\b(cat[eé]gorie\s+)?(tracking|documents|ai|security|s[eé]curit[eé]|account|compte|other|autre)\b",
    re.I,
)

_PROFILE_FOR_TASK = {
    TicketsTaskType.ticket_list: TicketsProfile.LIST,
    TicketsTaskType.ticket_detail: TicketsProfile.DETAIL,
    TicketsTaskType.ticket_details_batch: TicketsProfile.DETAILS_BATCH,
    TicketsTaskType.ticket_summary: TicketsProfile.SUMMARY,
    TicketsTaskType.ticket_reply: TicketsProfile.CONFIRM,
    TicketsTaskType.ticket_resolve: TicketsProfile.CONFIRM,
}


def _extract_reply_body(message: str) -> str | None:
    text = message or ""
    for pattern in _REPLY_BODY_PATTERNS:
        m = pattern.search(text)
        if m:
            body = (m.group(1) or "").strip()
            if len(body) >= 3:
                return body
    m = re.search(r"\bavec\s+(.+)$", text, re.I)
    if m:
        tail = m.group(1).strip()
        if len(tail) >= 8 and not re.search(r"\bticket\b", tail, re.I):
            return tail
    return None


def _is_draft_request(message: str) -> bool:
    return bool(_DRAFT_RE.search(message or ""))


def _target_status_from_message(message: str) -> str:
    if _WRITE_CLOSE_RE.search(message or ""):
        return "closed"
    return "resolved"


def _has_write_ticket_context(message: str, history_text: str) -> bool:
    return bool(
        re.search(r"\btickets?\b", message, re.I)
        or is_pronoun_ticket_reference(message)
        or extract_ticket_ref(message, history_text=history_text)
        or extract_ticket_number_token(message)
        or is_tickets_history_context(history_text)
        or has_tickets_list_data(history_text)
    )


def _build_write_plan(message: str, *, history_text: str = "", lang: str = "fr") -> TicketsPlan | None:
    text = _normalize(message)
    hist = history_text or ""
    if not _has_write_ticket_context(message, hist):
        return None

    ref = extract_ticket_ref(text, history_text=hist)
    is_resolve = bool(_WRITE_RESOLVE_RE.search(text) or _WRITE_CLOSE_RE.search(text))
    is_reply = bool(_WRITE_REPLY_RE.search(text))

    if is_resolve and not is_reply:
        return TicketsPlan(
            task_type=TicketsTaskType.ticket_resolve,
            profile=TicketsProfile.CONFIRM,
            ticket_id=ref,
            target_status=_target_status_from_message(message),
            raw_matches=["write_resolve"],
        )

    if is_reply:
        body = _extract_reply_body(message)
        want_draft = _is_draft_request(message) or not body
        return TicketsPlan(
            task_type=TicketsTaskType.ticket_reply,
            profile=TicketsProfile.CONFIRM,
            ticket_id=ref,
            reply_body=body or "",
            want_draft=want_draft,
            raw_matches=["write_reply"],
        )

    if lang == "en":
        question = "What would you like to do with this ticket — reply or mark resolved?"
    else:
        question = "Que souhaitez-vous faire sur ce ticket — répondre ou marquer résolu ?"
    return TicketsPlan(
        task_type=TicketsTaskType.ambiguous,
        profile=TicketsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=question,
        raw_matches=["write_ambiguous"],
    )


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _extract_status_filter(text: str) -> str | None:
    m = _STATUS_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token in {"ouvert", "ouverts", "open"}:
        return "open"
    if token in {"pending", "en cours"}:
        return "pending"
    if token in {"resolu", "résolu", "résolus", "resolus", "resolved"}:
        return "resolved"
    if token in {"ferme", "fermé", "fermés", "closed"}:
        return "closed"
    if token in {"tous", "all"}:
        return "all"
    return None


def _extract_priority_filter(text: str) -> str | None:
    m = _PRIORITY_RE.search(text)
    if not m:
        return None
    token = (m.group(2) or "").lower()
    if token in {"low", "basse"}:
        return "low"
    if token in {"medium", "moyenne"}:
        return "medium"
    if token in {"high", "haute", "urgent"}:
        return "high"
    return None


def _extract_category_filter(text: str) -> str | None:
    m = _CATEGORY_RE.search(text)
    if not m:
        return None
    token = (m.group(2) or "").lower()
    if token in {"sécurité", "securite", "security"}:
        return "security"
    if token in {"compte", "account"}:
        return "account"
    if token in {"autre", "other"}:
        return "other"
    if token in {"tracking", "documents", "ai"}:
        return token
    return None


def _apply_pdf_flag(plan: TicketsPlan, message: str) -> TicketsPlan:
    from app.services.client_phase3.pdf_postprocess import wants_pdf_format

    if wants_pdf_format(message):
        plan.want_pdf = True
    return plan


def _build_list_plan(text: str, *, raw: str, summary: bool = False) -> TicketsPlan:
    task = TicketsTaskType.ticket_summary if summary else TicketsTaskType.ticket_list
    profile = TicketsProfile.SUMMARY if summary else TicketsProfile.LIST
    plan = TicketsPlan(
        task_type=task,
        profile=profile,
        status_filter=_extract_status_filter(text),
        priority_filter=_extract_priority_filter(text),
        category_filter=_extract_category_filter(text),
        raw_matches=[raw],
    )
    if plan.status_filter or plan.priority_filter or plan.category_filter:
        plan.search_query = None
    return plan


def default_clarify_question(lang: str) -> str:
    if lang == "en":
        return (
            "Would you like to list support tickets, view ticket details, "
            "or get a summary (open, pending, resolved)?"
        )
    return (
        "Voulez-vous lister les tickets support, consulter le détail d'un ticket, "
        "ou obtenir un résumé (ouverts, en cours, résolus) ?"
    )


def default_clarify_plan(lang: str) -> TicketsPlan:
    return TicketsPlan(
        task_type=TicketsTaskType.ambiguous,
        profile=TicketsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=default_clarify_question(lang),
        raw_matches=["default_clarify"],
    )


def _build_details_batch_plan(text: str, *, raw: str) -> TicketsPlan:
    plan = TicketsPlan(
        task_type=TicketsTaskType.ticket_details_batch,
        profile=TicketsProfile.DETAILS_BATCH,
        status_filter=_extract_status_filter(text),
        priority_filter=_extract_priority_filter(text),
        category_filter=_extract_category_filter(text),
        raw_matches=[raw],
    )
    if plan.status_filter or plan.priority_filter or plan.category_filter:
        plan.search_query = None
    return plan


def classify_tickets_intent(message: str, *, history_text: str = "", lang: str = "fr") -> TicketsPlan:
    text = _normalize(message)
    hist = history_text or ""

    def _apply_notify_email(plan: TicketsPlan) -> TicketsPlan:
        from app.services.admin_client.email.email_action_offer import wants_notify_user_by_email

        if plan.task_type in {TicketsTaskType.ticket_reply, TicketsTaskType.ticket_resolve}:
            if wants_notify_user_by_email(message):
                plan.notify_email = True
        return plan

    def _finish(plan: TicketsPlan) -> TicketsPlan:
        return _apply_pdf_flag(_apply_notify_email(plan), message)

    if (_WRITE_REPLY_RE.search(text) or _WRITE_RESOLVE_RE.search(text) or _WRITE_CLOSE_RE.search(text)) and (
        _has_write_ticket_context(message, hist)
    ):
        write_plan = _build_write_plan(message, history_text=hist, lang=lang)
        if write_plan:
            return _finish(write_plan)

    if is_tickets_followup_message(text, history_text=hist) and not (
        is_tickets_list_utterance(message) or _LIST_RE.search(text)
    ):
        if _WRITE_REPLY_RE.search(text) or _WRITE_RESOLVE_RE.search(text) or _WRITE_CLOSE_RE.search(text):
            write_plan = _build_write_plan(message, history_text=hist, lang=lang)
            if write_plan:
                return _finish(write_plan)
        if _SUMMARY_RE.search(text):
            return _finish(_build_list_plan(text, raw="followup_summary", summary=True))
        if _DETAILS_PLURAL_RE.search(text):
            return _finish(_build_details_batch_plan(text, raw="followup_details_batch"))
        ref = extract_ticket_ref(text, history_text=hist)
        if ref or extract_ticket_number_token(text) or is_pronoun_ticket_reference(text):
            return _finish(
                TicketsPlan(
                    task_type=TicketsTaskType.ticket_detail,
                    profile=TicketsProfile.DETAIL,
                    ticket_id=ref,
                    raw_matches=["followup_detail"],
                )
            )
        idx = extract_list_row_index(text)
        if idx is not None:
            return _finish(
                TicketsPlan(
                    task_type=TicketsTaskType.ticket_detail,
                    profile=TicketsProfile.DETAIL,
                    raw_matches=["followup_ordinal"],
                )
            )
        return _finish(
            TicketsPlan(
                task_type=TicketsTaskType.ticket_detail,
                profile=TicketsProfile.DETAIL,
                raw_matches=["followup_detail"],
            )
        )

    if _SUMMARY_RE.search(text):
        return _finish(_build_list_plan(text, raw="summary", summary=True))
    if _DETAIL_RE.search(text) or extract_ticket_ref(text, history_text=hist) or extract_ticket_number_token(text):
        return _finish(
            TicketsPlan(
                task_type=TicketsTaskType.ticket_detail,
                profile=TicketsProfile.DETAIL,
                ticket_id=extract_ticket_ref(text, history_text=hist),
                raw_matches=["detail"],
            )
        )
    if _DETAILS_PLURAL_RE.search(text):
        return _finish(_build_details_batch_plan(text, raw="details_batch"))
    if is_tickets_list_utterance(message) or (
        _CLIENT_TICKETS_RE.search(text) and re.search(r"\btickets?\b", text, re.I)
    ):
        return _finish(_build_list_plan(text, raw="list"))

    if is_tickets_workspace(text, history_text=hist):
        if _CLIENT_TICKETS_RE.search(text) or extract_email_from_message(message):
            return _finish(_build_list_plan(text, raw="client_filter"))
        if score_tickets_soft(text) >= 2.5:
            if _SUMMARY_RE.search(text):
                return _finish(_build_list_plan(text, raw="workspace_summary", summary=True))
            return _finish(_build_list_plan(text, raw="workspace_list"))
        return _finish(default_clarify_plan(lang))

    return _finish(TicketsPlan(task_type=TicketsTaskType.ambiguous, raw_matches=["no_match"]))


def clarify_missing_reply_body(lang: str) -> TicketsPlan:
    return TicketsPlan(
        task_type=TicketsTaskType.ticket_reply,
        profile=TicketsProfile.CLARIFY,
        needs_clarification=True,
        clarification_question=(
            "Quel message souhaitez-vous envoyer au client (ou demandez un **brouillon**) ?"
            if lang == "fr"
            else "What message should I send to the client (or ask for a **draft**)?"
        ),
        raw_matches=["missing_reply_body"],
    )


@dataclass
class TargetTicketResolution:
    ticket_id: int | None = None
    ticket_number: str | None = None
    needs_clarification: bool = False
    clarification_question: str = ""
    candidates: list[dict[str, str]] | None = None


def _finalize_ticket_id(
    db: Session,
    ref: int,
    *,
    history_text: str,
    lang: str,
) -> TargetTicketResolution:
    resolved = resolve_ticket_id_from_context(db, ref, history_text=history_text)
    if resolved:
        return TargetTicketResolution(ticket_id=resolved)
    hint = format_ticket_ids_hint(history_text, lang=lang)
    if lang == "en":
        question = f"Ticket **#{ref}** not found.{hint}"
    else:
        question = f"Ticket **#{ref}** introuvable.{hint}"
    return TargetTicketResolution(
        needs_clarification=True,
        clarification_question=question,
    )


def resolve_target_ticket(
    db: Session,
    message: str,
    plan: TicketsPlan,
    *,
    history_text: str = "",
    lang: str = "fr",
) -> TargetTicketResolution:
    if plan.ticket_id:
        return _finalize_ticket_id(db, plan.ticket_id, history_text=history_text, lang=lang)

    text = message or ""
    ref = extract_ticket_ref(text, history_text=history_text)
    if ref is not None:
        return _finalize_ticket_id(db, ref, history_text=history_text, lang=lang)

    tkt_num = extract_ticket_number_token(text)
    if tkt_num:
        row = db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == tkt_num).limit(1))
        if row:
            return TargetTicketResolution(ticket_id=row.id, ticket_number=tkt_num)
        return TargetTicketResolution(
            needs_clarification=True,
            clarification_question=(
                f"Aucun ticket avec le numéro **{tkt_num}**."
                if lang == "fr"
                else f"No ticket with number **{tkt_num}**."
            ),
        )

    if has_tickets_list_data(history_text):
        idx = extract_list_row_index(text)
        if idx is not None:
            ids = list_ticket_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return TargetTicketResolution(ticket_id=ids[idx])
        m = re.search(r"\b(?:le|la)\s+(\d{1,3})\b", text, re.I)
        if m:
            idx = int(m.group(1)) - 1
            ids = list_ticket_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return TargetTicketResolution(ticket_id=ids[idx])

    if is_pronoun_ticket_reference(text) or plan.task_type == TicketsTaskType.ticket_detail:
        tid, tkt = resolve_pronoun_or_context(text, history_text)
        if tid:
            return TargetTicketResolution(ticket_id=tid)
        if tkt:
            row = db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == tkt).limit(1))
            if row:
                return TargetTicketResolution(ticket_id=row.id, ticket_number=tkt)

    if plan.search_query and plan.task_type == TicketsTaskType.ticket_list:
        return TargetTicketResolution()

    q = (plan.search_query or "").strip()
    if q:
        pattern = f"%{q}%"
        matches = list(
            db.scalars(
                select(SupportTicket)
                .where(
                    or_(
                        SupportTicket.subject.ilike(pattern),
                        SupportTicket.message.ilike(pattern),
                    )
                )
                .order_by(SupportTicket.created_at.desc())
                .limit(5)
            ).all()
        )
        if len(matches) == 1:
            return TargetTicketResolution(ticket_id=matches[0].id)
        if len(matches) > 1:
            return TargetTicketResolution(
                needs_clarification=True,
                clarification_question=(
                    "Plusieurs tickets correspondent — précisez #id ou TKT-…"
                    if lang == "fr"
                    else "Multiple tickets match — specify #id or TKT-…"
                ),
                candidates=[
                    {"id": str(t.id), "subject": (t.subject or "")[:80]}
                    for t in matches[:5]
                ],
            )

    if plan.task_type == TicketsTaskType.ticket_detail:
        return TargetTicketResolution(
            needs_clarification=True,
            clarification_question=(
                "Quel ticket ciblez-vous (#id, TKT-… ou numéro dans la liste) ?"
                if lang == "fr"
                else "Which ticket do you mean (#id, TKT-…, or list row number)?"
            ),
        )
    return TargetTicketResolution()
