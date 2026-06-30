"""Contexte structuré pour le chaînage de tâches mission (workflow multi-étapes)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.mission_task_catalog import (
    AGENT_LABELS,
    MissionTaskSpec,
    get_task_spec,
    normalize_agent_type,
)


def extract_chain_context(
    output: dict[str, Any],
    *,
    task_id: str | None = None,
    agent_type: str | None = None,
) -> dict[str, Any]:
    """Extrait IDs et références structurées depuis la sortie d'une étape."""
    ctx: dict[str, Any] = {}
    embedded = output.get("chain_context")
    if isinstance(embedded, dict):
        ctx.update(embedded)

    if output.get("security_incident_id") is not None:
        ctx["security_incident_id"] = int(output["security_incident_id"])

    incidents = output.get("security_incidents")
    if isinstance(incidents, list):
        ids = [int(i["id"]) for i in incidents if isinstance(i, dict) and i.get("id") is not None]
        if ids:
            ctx["security_incident_ids"] = ids

    target_ticket = output.get("target_ticket")
    if isinstance(target_ticket, dict) and target_ticket.get("ticket_id") is not None:
        ctx["ticket_id"] = int(target_ticket["ticket_id"])

    verification = output.get("verification")
    if isinstance(verification, dict) and verification.get("user_id") is not None:
        ctx["user_id"] = int(verification["user_id"])

    answer = str(output.get("task_answer") or output.get("analysis") or "")
    if answer:
        from app.services.admin_client.security.security_followup import list_incident_ids_from_history
        from app.services.admin_client.tickets.tickets_followup import list_ticket_ids_from_history

        sec_ids = list_incident_ids_from_history(answer)
        if sec_ids:
            ctx.setdefault("security_incident_ids", sec_ids)
        if not _is_security_incident_context(answer):
            ticket_ids = list_ticket_ids_from_history(answer)
            if ticket_ids:
                ctx.setdefault("ticket_ids", ticket_ids)

    if task_id and agent_type:
        canonical = normalize_agent_type(agent_type)
        if canonical == "security" and task_id == "incident_detail" and ctx.get("security_incident_id"):
            ctx["last_security_incident_id"] = ctx["security_incident_id"]

    return ctx


def merge_chain_context(base: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (new or {}).items():
        if value is None:
            continue
        if key.endswith("_ids") and isinstance(value, list):
            merged[key] = value
        else:
            merged[key] = value
    return merged


_AGENT_CONTEXT_KEYS: dict[str, frozenset[str]] = {
    "security": frozenset({"security_incident_id", "security_incident_ids", "last_security_incident_id"}),
    "support": frozenset({"ticket_id", "ticket_ids"}),
    "users": frozenset({"user_id", "user_email"}),
    "logs": frozenset(),
    "tracking": frozenset(),
    "reports": frozenset(),
}

_UNIVERSAL_HANDOFF_KEYS = frozenset({"user_id", "user_email", "prior_agent_type", "prior_task_id"})
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_SECURITY_TABLE_MARKERS = re.compile(
    r"Incidents s[eé]curit[eé]|Security incidents|\|\s*Menace\s*\||prompt_injection|data_exfiltration",
    re.I,
)


def _is_security_incident_context(text: str) -> bool:
    return bool(_SECURITY_TABLE_MARKERS.search(text or ""))


def enrich_chain_context_from_prior_summary(
    chain_context: dict[str, Any],
    prior_summary: str,
    *,
    prior_agent: str | None = None,
    prior_task_id: str | None = None,
) -> dict[str, Any]:
    """Enrichit le contexte structuré depuis le texte de l'étape précédente (passage inter-agents)."""
    ctx = dict(chain_context or {})
    text = prior_summary or ""

    if prior_agent:
        ctx["prior_agent_type"] = normalize_agent_type(prior_agent)
    if prior_task_id:
        ctx["prior_task_id"] = prior_task_id

    if not ctx.get("user_email"):
        email_match = _EMAIL_RE.search(text)
        if email_match:
            ctx["user_email"] = email_match.group(0)

    if not ctx.get("ticket_id") and not ctx.get("ticket_ids"):
        from app.services.admin_client.tickets.tickets_followup import list_ticket_ids_from_history

        ticket_ids = list_ticket_ids_from_history(text)
        if ticket_ids:
            ctx.setdefault("ticket_ids", ticket_ids)
            if len(ticket_ids) == 1:
                ctx.setdefault("ticket_id", ticket_ids[0])

    return ctx


def filter_chain_context_for_agent(chain_context: dict[str, Any], agent_type: str) -> dict[str, Any]:
    """Sous-ensemble par agent (utilisé pour affichage ciblé, pas pour bloquer le handoff)."""
    canonical = normalize_agent_type(agent_type)
    allowed = _AGENT_CONTEXT_KEYS.get(canonical, frozenset()) | _UNIVERSAL_HANDOFF_KEYS
    return {k: v for k, v in (chain_context or {}).items() if k in allowed and v is not None}


def handoff_context_for_next_task(
    prior_summary: str,
    chain_context: dict[str, Any],
    *,
    prior_agent: str | None,
    next_agent: str,
    next_task_id: str | None,
    prior_task_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Prépare le contexte pour l'étape suivante.
    Si consumes_prior : transmet texte + contexte (même agent ou agents différents).
    """
    next_canonical = normalize_agent_type(next_agent)
    next_spec = get_task_spec(next_canonical, next_task_id or "") if next_task_id else None

    if not next_spec or not next_spec.consumes_prior:
        return "", {}

    enriched = enrich_chain_context_from_prior_summary(
        chain_context,
        prior_summary,
        prior_agent=prior_agent,
        prior_task_id=prior_task_id,
    )

    if not prior_summary and not enriched:
        return "", enriched

    return prior_summary, enriched


def advance_chain_state(
    prior_summary: str,
    chain_context: dict[str, Any],
    output: dict[str, Any],
    *,
    task_id: str | None,
    agent_type: str,
) -> tuple[str, dict[str, Any]]:
    """
    Met à jour le résumé / contexte pour l'étape suivante.
    Ne remplace pas le résumé si l'étape courante ne produit pas de contexte (exports, actions terminales).
    """
    canonical = normalize_agent_type(agent_type)
    spec = get_task_spec(canonical, task_id or "") if task_id else None
    extracted = extract_chain_context(output, task_id=task_id, agent_type=canonical)
    merged_context = merge_chain_context(chain_context, extracted)

    if spec and not spec.produces_context:
        return prior_summary, chain_context

    summary = str(output.get("task_answer") or output.get("analysis") or prior_summary)
    if spec and spec.produces_context:
        return summary, merged_context
    if not spec:
        return summary, merged_context
    return prior_summary, chain_context


def enrich_description_from_chain(
    custom_desc: str,
    spec: MissionTaskSpec | None,
    chain_context: dict[str, Any],
) -> str:
    """Pré-remplit une description vide à partir du contexte structuré (sans écraser #2, etc.)."""
    desc = (custom_desc or "").strip()
    if not spec or not spec.consumes_prior or not chain_context:
        return desc
    if len(desc) >= 2:
        return desc

    task_key = spec.task_id
    if task_key == "incident_detail":
        if chain_context.get("security_incident_id"):
            return f"incident #{chain_context['security_incident_id']}"
        ids = chain_context.get("security_incident_ids") or []
        if len(ids) == 1:
            return f"incident #{ids[0]}"

    if task_key in ("ticket_detail", "ticket_reply", "ticket_resolve"):
        if chain_context.get("ticket_id"):
            return f"ticket #{chain_context['ticket_id']}"
        ids = chain_context.get("ticket_ids") or []
        if len(ids) == 1:
            return f"ticket #{ids[0]}"
        if chain_context.get("user_email"):
            return f"ticket du client {chain_context['user_email']}"

    if task_key in (
        "user_detail",
        "user_logs",
        "user_permissions",
        "user_suspend",
        "user_reactivate",
        "user_delete",
        "user_reset_password",
    ):
        if chain_context.get("user_id"):
            return f"utilisateur #{chain_context['user_id']}"
        if chain_context.get("user_email"):
            return str(chain_context["user_email"])

    if task_key == "incident_detail" and chain_context.get("user_email"):
        return f"incident lié à {chain_context['user_email']}"

    return desc


def format_prior_context_header(chain_context: dict[str, Any]) -> str:
    """En-tête du bloc texte issu de l'étape précédente."""
    prior_agent = chain_context.get("prior_agent_type")
    if not prior_agent:
        return "Contexte étape précédente :"
    label = AGENT_LABELS.get(str(prior_agent), prior_agent)
    return f"Contexte étape précédente ({label}) :"


def format_chain_context_block(chain_context: dict[str, Any]) -> str:
    """Bloc texte compact pour les outils qui lisent le prompt mission."""
    if not chain_context:
        return ""
    lines: list[str] = []
    if chain_context.get("prior_agent_type"):
        pa = chain_context["prior_agent_type"]
        lines.append(f"Étape précédente : {AGENT_LABELS.get(str(pa), pa)}")
    sec_ids = chain_context.get("security_incident_ids")
    if isinstance(sec_ids, list) and sec_ids:
        shown = ", ".join(f"#{i}" for i in sec_ids[:15])
        lines.append(f"Incidents listés (IDs) : {shown}")
    if chain_context.get("security_incident_id") is not None:
        lines.append(f"Incident cible : #{chain_context['security_incident_id']}")
    ticket_ids = chain_context.get("ticket_ids")
    if isinstance(ticket_ids, list) and ticket_ids:
        lines.append(f"Tickets listés (IDs) : {', '.join(f'#{i}' for i in ticket_ids[:15])}")
    if chain_context.get("ticket_id") is not None:
        lines.append(f"Ticket cible : #{chain_context['ticket_id']}")
    if chain_context.get("user_id") is not None:
        lines.append(f"Utilisateur cible : #{chain_context['user_id']}")
    if chain_context.get("user_email"):
        lines.append(f"E-mail cible : {chain_context['user_email']}")
    if not lines:
        return ""
    return "Contexte structuré :\n" + "\n".join(lines)


def resolve_user_id_from_chain(db: Session, chain_context: dict[str, Any]) -> int | None:
    """Résout un user_id depuis le contexte chaîné (ticket support, e-mail, etc.)."""
    if not chain_context:
        return None
    if chain_context.get("user_id") is not None:
        return int(chain_context["user_id"])

    email = chain_context.get("user_email")
    if email:
        from sqlalchemy import select

        from app.models.user import User

        user = db.scalars(select(User).where(User.email.ilike(str(email))).limit(1)).first()
        if user:
            return int(user.id)

    ticket_id = chain_context.get("ticket_id")
    if ticket_id is None:
        ticket_ids = chain_context.get("ticket_ids") or []
        if isinstance(ticket_ids, list) and len(ticket_ids) == 1:
            ticket_id = ticket_ids[0]
    if ticket_id is not None:
        from app.services.admin_client.tickets import tickets_tool

        try:
            detail = tickets_tool.get_ticket_detail(db, int(ticket_id))
            uid = detail.get("user_id")
            return int(uid) if uid is not None else None
        except Exception:
            return None

    return None


def rebuild_chain_state_from_outputs(
    outputs: list[tuple[dict[str, Any], str | None, str]],
) -> tuple[str, dict[str, Any], str | None, str | None]:
    """Reconstruit résumé + contexte + dernier agent/tâche producteurs."""
    prior_summary = ""
    chain_context: dict[str, Any] = {}
    prior_agent: str | None = None
    prior_task_id: str | None = None
    for output, task_id, agent_type in outputs:
        prior_summary, chain_context = advance_chain_state(
            prior_summary,
            chain_context,
            output,
            task_id=task_id,
            agent_type=agent_type,
        )
        canonical = normalize_agent_type(agent_type)
        spec = get_task_spec(canonical, task_id or "") if task_id else None
        if spec and spec.produces_context:
            prior_agent = canonical
            prior_task_id = task_id
    return prior_summary, chain_context, prior_agent, prior_task_id
