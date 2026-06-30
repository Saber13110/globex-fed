"""Résolution tâches mission — catalogue → texte exécutable + validation rôle."""

from __future__ import annotations

from typing import Any

from app.services.mission_chain_context import (
    enrich_description_from_chain,
    format_chain_context_block,
    format_prior_context_header,
)
from app.services.mission_task_catalog import (
    AGENT_KEYWORDS,
    AGENT_LABELS,
    MissionTaskSpec,
    get_task_spec,
    normalize_agent_type,
    runtime_agent_type,
)

PRIOR_CONTEXT_MARKER = "Contexte étape précédente :"
PRIOR_CONTEXT_LIMIT_DEFAULT = 800
PRIOR_CONTEXT_LIMIT_CHAIN = 2500


def split_prior_context(task_text: str) -> tuple[str, str]:
    """Sépare le texte de tâche courant du bloc contexte workflow précédent."""
    text = task_text or ""
    marker = PRIOR_CONTEXT_MARKER
    if marker not in text:
        return text.strip(), ""
    idx = text.index(marker)
    user_part = text[:idx].strip()
    prior_part = text[idx + len(marker) :].strip()
    return user_part, prior_part


def prior_context_limit_for_task(spec: MissionTaskSpec | None) -> int:
    if spec and spec.consumes_prior:
        return PRIOR_CONTEXT_LIMIT_CHAIN
    return PRIOR_CONTEXT_LIMIT_DEFAULT


def workflow_agent_for_task(wf: dict[str, Any], task_node_id: str) -> str | None:
    """Remonte le graphe pour trouver l'agent lié à une tâche (BFS inverse)."""
    nodes_list = wf.get("nodes") or []
    nodes = {n["id"]: n for n in nodes_list}
    edges = wf.get("edges") or []
    in_edges: dict[str, list[str]] = {}
    for e in edges:
        in_edges.setdefault(e["to"], []).append(e["from"])

    queue = [task_node_id]
    visited: set[str] = set()
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes.get(nid)
        if node and node.get("type") == "agent":
            at = (node.get("data") or {}).get("agentType")
            if at:
                return str(at)
        for prev in in_edges.get(nid, []):
            if prev not in visited:
                queue.append(prev)
    agent_nodes = [n for n in nodes_list if n.get("type") == "agent"]
    if len(agent_nodes) == 1:
        return (agent_nodes[0].get("data") or {}).get("agentType")
    return None


def resolve_task_from_node(
    agent_type: str,
    node_data: dict[str, Any],
    *,
    prior_summary: str = "",
    chain_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le texte de tâche et métadonnées depuis un nœud workflow."""
    canonical = normalize_agent_type(agent_type)
    task_id = str(node_data.get("taskId") or node_data.get("task_id") or "").strip()
    custom_desc = str(node_data.get("description") or "").strip()
    label = str(node_data.get("label") or "Tâche").strip()
    priority = int(node_data.get("priority") or 100)
    ctx = chain_context or {}

    spec = get_task_spec(canonical, task_id) if task_id else None
    prior_limit = prior_context_limit_for_task(spec)
    custom_desc = enrich_description_from_chain(custom_desc, spec, ctx)

    if spec and spec.task_id != "custom":
        parts = [spec.default_prompt]
        if custom_desc:
            parts.append(f"Précisions : {custom_desc}")
        if spec.consumes_prior:
            if prior_summary:
                header = format_prior_context_header(ctx)
                parts.append(f"{header} {prior_summary[:prior_limit]}")
            struct_block = format_chain_context_block(ctx)
            if struct_block:
                parts.append(struct_block)
        task_text = "\n\n".join(p for p in parts if p)
        return {
            "task_text": task_text,
            "task_id": spec.task_id,
            "label": spec.label or label,
            "action_type": spec.action_type,
            "tool_hint": spec.tool_hint,
            "agent_type": canonical,
            "priority": priority,
            "catalog_match": True,
        }

    if spec and spec.task_id == "custom":
        task_text = custom_desc
        if prior_summary or ctx:
            if prior_summary:
                task_text = f"{task_text}\n\n{PRIOR_CONTEXT_MARKER} {prior_summary[:prior_limit]}"
            struct_block = format_chain_context_block(ctx)
            if struct_block:
                task_text = f"{task_text}\n\n{struct_block}"
        return {
            "task_text": task_text,
            "task_id": "custom",
            "label": label or spec.label,
            "action_type": spec.action_type,
            "tool_hint": None,
            "agent_type": canonical,
            "priority": priority,
            "catalog_match": bool(custom_desc),
        }

    # Legacy : pas de taskId — description libre uniquement
    task_text = custom_desc
    if prior_summary and task_text:
        task_text = f"{task_text}\n\n{PRIOR_CONTEXT_MARKER} {prior_summary[:PRIOR_CONTEXT_LIMIT_DEFAULT]}"
    return {
        "task_text": task_text,
        "task_id": task_id or None,
        "label": label,
        "action_type": _default_action_type(canonical),
        "tool_hint": None,
        "agent_type": canonical,
        "priority": priority,
        "catalog_match": False,
    }


def _default_action_type(agent_type: str) -> str:
    defaults = {
        "logs": "analyze_logs",
        "support": "analyze_tickets",
        "users": "analyze_users",
        "security": "analyze_security",
        "tracking": "analyze_tracking",
        "reports": "generate_summary",
    }
    return defaults.get(normalize_agent_type(agent_type), "analyze_only")


def assess_task_role(
    task: str,
    agent_type: str,
    *,
    task_id: str | None = None,
    legacy_meta: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Valide qu'une tâche correspond à l'agent.
    Si task_id catalogue valide → match garanti (évite faux positifs keywords).
    """
    canonical = normalize_agent_type(agent_type)
    label = AGENT_LABELS.get(canonical, AGENT_LABELS.get(agent_type, agent_type))

    if task_id:
        spec = get_task_spec(canonical, task_id)
        if spec and spec.task_id != "custom":
            return {
                "matches": True,
                "score": 10,
                "reason": f"Tâche catalogue « {spec.label} » pour {label}.",
                "suggested_agent": None,
                "task_id": spec.task_id,
            }
        if spec and spec.task_id == "custom":
            ok = len((task or "").strip()) >= 10
            return {
                "matches": ok,
                "score": 1 if ok else 0,
                "reason": (
                    f"Tâche libre — description requise (min. 10 caractères)."
                    if not ok
                    else f"Tâche libre pour {label}."
                ),
                "suggested_agent": None if ok else canonical,
                "task_id": "custom",
            }

    task_l = (task or "").lower()
    keywords = AGENT_KEYWORDS.get(canonical)
    if not keywords and legacy_meta:
        meta = legacy_meta.get(agent_type) or legacy_meta.get(canonical, {})
        keywords = tuple(meta.get("keywords") or ())

    if keywords:
        score = sum(1 for kw in keywords if kw in task_l)
        if score >= 1:
            return {
                "matches": True,
                "score": score,
                "reason": f"Tâche alignée avec le {label}.",
                "suggested_agent": None,
            }

    best_agent = "reports"
    best_score = 0
    for atype, kws in AGENT_KEYWORDS.items():
        if atype == canonical:
            continue
        s = sum(1 for kw in kws if kw in task_l)
        if s > best_score:
            best_score = s
            best_agent = atype

    if best_score >= 1:
        best_label = AGENT_LABELS.get(best_agent, best_agent)
        return {
            "matches": False,
            "score": 0,
            "reason": (
                f"Cette tâche correspond plutôt au **{best_label}**, "
                f"pas au {label}."
            ),
            "suggested_agent": best_agent,
        }

    return {
        "matches": False,
        "score": 0,
        "reason": (
            f"Le {label} ne traite pas ce type de demande. "
            "Choisissez un autre agent ou une tâche du catalogue."
        ),
        "suggested_agent": "reports",
    }


def catalog_mission_tool(resolved: dict[str, Any]) -> str | None:
    """Outil imposé par le catalogue mission (prioritaire sur le cerveau LLM)."""
    if resolved.get("tool_hint"):
        return str(resolved["tool_hint"])
    if not resolved.get("catalog_match"):
        return None
    action = str(resolved.get("action_type") or "")
    if action in (
        "analyze_security",
        "analyze_notifications",
        "analyze_logs",
        "analyze_users",
        "analyze_tickets",
        "analyze_tracking",
        "generate_summary",
        "export_activity_logs_pdf",
        "export_activity_logs_excel",
        "export_tracking_excel",
        "export_and_email_tracking",
        "suspend_user",
        "reactivate_user",
    ):
        return action
    return None


def security_plan_for_catalog_task(task_id: str | None, *, limit: int = 30):
    """Plan Security IDS aligné sur le catalogue mission (compose déterministe chat)."""
    from app.services.admin_client.security.security_types import (
        SecurityPlan,
        SecurityProfile,
        SecurityTaskType,
    )

    mapping: dict[str, tuple[SecurityTaskType, SecurityProfile]] = {
        "incident_list": (SecurityTaskType.security_incident_list, SecurityProfile.LIST),
        "incident_detail": (SecurityTaskType.security_incident_detail, SecurityProfile.DETAIL),
        "incident_summary": (SecurityTaskType.security_incident_summary, SecurityProfile.SUMMARY),
        "security_scan": (SecurityTaskType.security_scan, SecurityProfile.SCAN),
        "security_report": (SecurityTaskType.security_report, SecurityProfile.REPORT),
    }
    if not task_id or task_id == "custom":
        return None
    pair = mapping.get(task_id)
    if not pair:
        return None
    task_type, profile = pair
    return SecurityPlan(
        task_type=task_type,
        profile=profile,
        status_filter="open" if task_type == SecurityTaskType.security_incident_list else None,
        limit=limit,
    )


def support_plan_for_catalog_task(task_id: str | None, *, limit: int = 30):
    """Plan tickets aligné sur le catalogue mission."""
    from app.services.admin_client.tickets.tickets_types import (
        TicketsPlan,
        TicketsProfile,
        TicketsTaskType,
    )

    mapping: dict[str, tuple[TicketsTaskType, TicketsProfile]] = {
        "ticket_list": (TicketsTaskType.ticket_list, TicketsProfile.LIST),
        "ticket_detail": (TicketsTaskType.ticket_detail, TicketsProfile.DETAIL),
    }
    if not task_id or task_id == "custom":
        return None
    pair = mapping.get(task_id)
    if not pair:
        return None
    task_type, profile = pair
    return TicketsPlan(
        task_type=task_type,
        profile=profile,
        status_filter="open" if task_type == TicketsTaskType.ticket_list else None,
        limit=limit,
    )


def users_plan_for_catalog_task(task_id: str | None, *, limit: int = 30):
    """Plan utilisateurs aligné sur le catalogue mission."""
    from app.services.admin_client.users.users_types import UsersPlan, UsersProfile, UsersTaskType

    mapping: dict[str, tuple[UsersTaskType, UsersProfile]] = {
        "user_list": (UsersTaskType.user_list, UsersProfile.LIST),
        "user_detail": (UsersTaskType.user_detail, UsersProfile.DETAIL),
        "user_logs": (UsersTaskType.user_logs, UsersProfile.LOGS),
        "user_permissions": (UsersTaskType.user_permissions, UsersProfile.PERMISSIONS),
    }
    if not task_id or task_id == "custom":
        return None
    pair = mapping.get(task_id)
    if not pair:
        return None
    task_type, profile = pair
    return UsersPlan(task_type=task_type, profile=profile, limit=limit)


def task_wants_security_incident_list(task: str, catalog_task_id: str | None = None) -> bool:
    if catalog_task_id == "incident_list":
        return True
    t = (task or "").lower()
    return bool(
        any(k in t for k in ("lister", "liste", "list"))
        and any(k in t for k in ("incident", "incidents"))
    )


def sort_task_nodes(task_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordre stable : parcours graphe (BFS) puis priorité (plus petit = plus tôt)."""
    indexed = list(enumerate(task_nodes))
    indexed.sort(
        key=lambda pair: (
            pair[0],
            int((pair[1].get("data") or {}).get("priority") or 100),
        )
    )
    return [n for _, n in indexed]
