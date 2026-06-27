"""Service — missions agent IA (plan, exécution, approbations)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.activity_log import ActivityLog
from app.models.agent_approval_request import AgentApprovalRequest
from app.models.agent_execution_log import AgentExecutionLog
from app.models.agent_mission import AgentMission
from app.models.agent_mission_message import AgentMissionMessage
from app.models.agent_mission_step import AgentMissionStep
from app.models.platform_notification import PlatformNotification
from app.models.security_incident import SecurityIncident
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole, UserStatus
from app.schemas.agent_missions import (
    AgentMissionCreate,
    AgentMissionDetailResponse,
    AgentMissionListItem,
    AgentMissionListResponse,
    AgentMissionMessageRead,
    AgentMissionRead,
    AgentMissionResults,
    AgentMissionStepRead,
    AgentMissionWorkflowUpdate,
    AgentApprovalRead,
    AgentExecutionLogRead,
    AgentStepResultRead,
)

from app.services.admin_agent_runtime import (
    execute_admin_mission_task,
    execute_approved_bulk_users,
    execute_approved_email_attachment,
    execute_approved_support_reply,
)
from app.services.admin_agent_tools import (
    admin_find_tracking_rows,
    aggregate_user_behavior,
    extract_tracking_numbers,
    find_ticket_for_task,
    ticket_context_dict,
)
from app.services.notifications_service import _upsert as upsert_platform_notification

SENSITIVE_ACTIONS = frozenset(
    {
        "send_support_reply",
        "suspend_user",
        "change_status",
        "send_notification",
        "delete_data",
    }
)

AGENT_LABELS = {
    "logs": "Logs Agent",
    "support": "Support Agent",
    "users": "Users Agent",
    "tracking": "Tracking Agent",
    "notifications": "Notifications Agent",
    "summary": "Summary Agent",
}

AGENT_ROLE_META: dict[str, dict[str, Any]] = {
    "logs": {
        "tools": ["Lire activity logs", "Filtrer WARNING/CRITICAL", "Détecter anomalies"],
        "keywords": [
            "log", "logs", "journal", "audit", "activité", "activite", "anomalie",
            "erreur", "warning", "critical", "événement", "evenement", "historique",
            "pdf", "télécharger", "telecharger", "export", "fichier", "download",
        ],
        "action": "analyze_logs",
    },
    "support": {
        "tools": ["Lire tickets ouverts", "Analyser priorités", "Préparer réponses"],
        "keywords": [
            "ticket", "support", "client", "réponse", "reponse", "urgent", "plainte",
            "aide", "demande", "message client",
        ],
        "action": "analyze_tickets",
    },
    "users": {
        "tools": ["Lister comptes", "Détecter suspendus", "Analyser rôles"],
        "keywords": [
            "utilisateur", "user", "compte", "employé", "employe", "client", "suspend",
            "inactif", "permission", "rôle", "role", "invitation",
        ],
        "action": "analyze_users",
    },
    "tracking": {
        "tools": ["Lire expéditions", "Détecter retards", "Analyser statuts FedEx"],
        "keywords": [
            "tracking", "colis", "expédition", "expedition", "livraison", "fedex",
            "retard", "shipment", "numéro de suivi", "numero de suivi",
        ],
        "action": "analyze_tracking",
    },
    "notifications": {
        "tools": ["Lire notifications", "Incidents sécurité", "Alertes non lues"],
        "keywords": [
            "notification", "alerte", "attaque", "attack", "sécurité", "securite",
            "incident", "ids", "tentative", "intrusion", "menace",
        ],
        "action": "analyze_notifications",
    },
    "summary": {
        "tools": ["Agréger données", "Synthétiser KPIs", "Rapport exécutif"],
        "keywords": [
            "résumé", "resume", "synthèse", "synthese", "rapport", "bilan",
            "overview", "global", "jour", "semaine", "performance",
        ],
        "action": "generate_summary",
    },
}

logger = logging.getLogger(__name__)

ADMIN_MISSION_SYSTEM_PROMPT = (
    "Tu es un agent d'analyse pour l'administrateur de la plateforme Globex FedEx. "
    "Tu reçois des données réelles (logs, notifications, incidents sécurité, tickets). "
    "Réponds UNIQUEMENT à la tâche demandée par l'admin, en français. "
    "Structure ta réponse en : Constat, Éléments identifiés, Recommandations. "
    "Ne répète pas un plan générique. Cite des faits concrets issus des données. "
    "RÈGLE CRITIQUE : ne dis JAMAIS qu'une action a été exécutée (suspension, envoi, modification) "
    "si les données ne le confirment pas explicitement. Si seule une analyse est faite, dis-le clairement."
)


def _parse_workflow_builder(plan_json: str) -> dict[str, Any] | None:
    if not plan_json or not plan_json.strip():
        return None
    try:
        data = json.loads(plan_json)
        if data.get("version") == 3 and data.get("type") == "builder":
            return data
    except json.JSONDecodeError:
        pass
    return None


def _workflow_ordered_tasks(wf: dict[str, Any]) -> list[dict[str, Any]]:
    """Retourne les nœuds tâche dans l'ordre du graphe (BFS depuis le déclencheur)."""
    nodes_list = wf.get("nodes") or []
    nodes = {n["id"]: n for n in nodes_list}
    edges = wf.get("edges") or []
    out_edges: dict[str, list[str]] = {}
    for e in edges:
        out_edges.setdefault(e["from"], []).append(e["to"])

    starts = [n for n in nodes_list if n.get("type") == "timing"]
    if not starts:
        in_targets = {e["to"] for e in edges}
        starts = [n for n in nodes_list if n["id"] not in in_targets]
    if not starts:
        return [n for n in nodes_list if n.get("type") == "task"]

    task_order: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue = [starts[0]["id"]]

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes.get(nid)
        if node and node.get("type") == "task":
            task_order.append(node)
        for nxt in out_edges.get(nid, []):
            if nxt not in visited:
                queue.append(nxt)

    return task_order


def _parse_users_task_intent(task: str) -> str:
    """Détecte suspendre / réactiver / analyse seule."""
    task_l = (task or "").lower()
    if re.search(r"\b(r[eé]activ|restaur|d[eé]bloqu)", task_l):
        return "reactivate_user"
    if re.search(r"\b(suspend|suspendre|bloqu|d[eé]sactiv)", task_l):
        return "suspend_user"
    return "analyze_users"


def _find_user_for_task(db: Session, task: str) -> User | None:
    """Résout un utilisateur par #id, email ou nom/compte mentionné."""
    task_l = (task or "").lower()

    id_match = re.search(r"(?:user|utilisateur|compte)\s*#(\d+)", task_l)
    if id_match:
        return db.get(User, int(id_match.group(1)))

    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", task)
    if email_match:
        return db.scalar(select(User).where(User.email == email_match.group(0)))

    name_match = re.search(
        r"(?:compte|user|utilisateur)\s+[\"']?([a-z0-9._-]+)[\"']?",
        task_l,
    )
    if name_match:
        token = name_match.group(1)
        if token.isdigit():
            return db.get(User, int(token))
        return db.scalar(
            select(User).where(
                or_(
                    User.full_name.ilike(f"%{token}%"),
                    User.email.ilike(f"%{token}%"),
                )
            )
        )

    # Dernier recours : mot unique significatif (ex. « sak »)
    words = [w for w in re.findall(r"[a-z0-9._-]+", task_l) if len(w) >= 3]
    skip = {
        "veux", "vouloir", "compte", "user", "utilisateur", "suspendre", "suspend",
        "reactiver", "réactiver", "this", "ce", "cette", "le", "la", "les", "des", "pour",
    }
    for word in reversed(words):
        if word in skip:
            continue
        found = db.scalar(
            select(User).where(
                or_(User.full_name.ilike(f"%{word}%"), User.email.ilike(f"%{word}%"))
            )
        )
        if found:
            return found
    return None


def _user_verification_snapshot(user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
    }


def _execute_user_sensitive_action(
    db: Session,
    *,
    action_type: str,
    user: User,
    actor_admin_id: int,
    reason: str,
) -> tuple[bool, dict[str, Any]]:
    """Exécute suspend/reactivate et vérifie le statut en base."""
    from app.services.security_ids_service import reactivate_user, suspend_user

    status_before = user.status
    ok = False
    if action_type == "suspend_user":
        ok = suspend_user(db, user.id, reason=reason, actor_admin_id=actor_admin_id)
    elif action_type == "reactivate_user":
        ok = reactivate_user(db, user.id, actor_admin_id=actor_admin_id)

    db.refresh(user)
    status_after = user.status
    expected = UserStatus.suspended.value if action_type == "suspend_user" else UserStatus.active.value
    verified = status_after == expected

    verification = {
        "user_id": user.id,
        "email": user.email,
        "status_before": status_before,
        "status_after": status_after,
        "expected_status": expected,
        "verified": verified and ok,
        "action_ok": ok,
    }
    return ok and verified, verification


def _execute_users_agent_mission(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    actor_admin_id: int,
    approved: bool = False,
) -> dict[str, Any]:
    """Users Agent : action réelle si demandée, sinon analyse honnête."""
    task = mission.task_description
    intent = _parse_users_task_intent(task)
    context = _gather_mission_context(db, mission)
    output: dict[str, Any] = {
        "agent_type": "users",
        "task": task,
        "intent": intent,
        "action_executed": False,
        "needs_approval": False,
        "analysis_only": intent == "analyze_users",
    }

    if intent in ("suspend_user", "reactivate_user"):
        user = _find_user_for_task(db, task)
        if not user:
            output.update(
                {
                    "action": intent,
                    "error": "user_not_found",
                    "task_answer": (
                        "NON FAIT — Utilisateur introuvable.\n\n"
                        f"Tâche : « {task} »\n"
                        "Précisez l'email, le #id ou le nom exact du compte."
                    ),
                }
            )
            step.action_type = intent
            return output

        output["target_user"] = _user_verification_snapshot(user)

        if user.role == UserRole.admin.value:
            output.update(
                {
                    "action": intent,
                    "error": "cannot_modify_admin",
                    "task_answer": (
                        "NON FAIT — Impossible de suspendre ou modifier un compte administrateur."
                    ),
                }
            )
            step.action_type = intent
            return output

        if intent == "suspend_user" and user.status == UserStatus.suspended.value:
            output.update(
                {
                    "action": intent,
                    "action_executed": False,
                    "already_in_state": True,
                    "verification": _user_verification_snapshot(user),
                    "task_answer": (
                        f"INFORMATION — Le compte {user.email} est déjà suspendu.\n"
                        f"Statut vérifié en base : {user.status}"
                    ),
                }
            )
            step.action_type = intent
            return output

        if intent == "reactivate_user" and user.status == UserStatus.active.value:
            output.update(
                {
                    "action": intent,
                    "action_executed": False,
                    "already_in_state": True,
                    "verification": _user_verification_snapshot(user),
                    "task_answer": (
                        f"INFORMATION — Le compte {user.email} est déjà actif.\n"
                        f"Statut vérifié en base : {user.status}"
                    ),
                }
            )
            step.action_type = intent
            return output

        reason = f"Mission agent #{mission.id} — {task[:200]}"
        step.action_type = intent
        step.is_sensitive = True

        if mission.require_approval_sensitive and not approved:
            output.update(
                {
                    "action": intent,
                    "needs_approval": True,
                    "task_answer": (
                        f"EN ATTENTE D'APPROBATION — Action demandée : {intent.replace('_', ' ')} "
                        f"pour {user.email} (#{user.id}).\n"
                        "Validez la demande de permission pour exécuter réellement l'action."
                    ),
                    "approval_payload": {
                        "action_type": intent,
                        "user_id": user.id,
                        "email": user.email,
                        "reason": reason,
                    },
                }
            )
            return output

        ok, verification = _execute_user_sensitive_action(
            db,
            action_type=intent,
            user=user,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
        output["verification"] = verification
        output["action_executed"] = ok
        if ok:
            label = "suspendu" if intent == "suspend_user" else "réactivé"
            output["task_answer"] = (
                f"FAIT — Compte {user.email} (#{user.id}) {label}.\n"
                f"Vérification : {verification['status_before']} → {verification['status_after']}"
            )
        else:
            output["task_answer"] = (
                f"NON FAIT — L'action {intent} a échoué pour {user.email}.\n"
                f"Statut actuel en base : {verification['status_after']}"
            )
        output["action"] = intent
        return output

    # Analyse seule (pas d'action destructive)
    step.action_type = "analyze_users"
    output["action"] = "analyze_users"
    output["users_total"] = context.get("users_total", 0)
    output["users_suspended"] = context.get("users_suspended", 0)
    task_answer = _mission_llm_analyze(mission, step, context)
    if not task_answer:
        task_answer = _fallback_task_answer(mission, step, context)
    output["task_answer"] = (
        f"ANALYSE SEULEMENT (aucune modification de compte).\n\n{task_answer}"
    )
    output["analysis"] = output["task_answer"]
    return output


def _workflow_output_destinations(wf: dict[str, Any]) -> list[str]:
    return [
        n.get("data", {}).get("destination", "results_panel")
        for n in (wf.get("nodes") or [])
        if n.get("type") == "output"
    ]


def _assess_task_role(task: str, agent_type: str) -> dict[str, Any]:
    """Vérifie si la tâche correspond au rôle de l'agent choisi."""
    task_l = (task or "").lower()
    meta = AGENT_ROLE_META.get(agent_type, AGENT_ROLE_META["summary"])

    if agent_type == "summary":
        return {
            "matches": True,
            "score": 1,
            "reason": "L'agent Résumé traite les demandes globales et rapports.",
            "suggested_agent": None,
        }

    score = sum(1 for kw in meta["keywords"] if kw in task_l)
    if score >= 1:
        return {
            "matches": True,
            "score": score,
            "reason": f"Tâche alignée avec le {AGENT_LABELS[agent_type]}.",
            "suggested_agent": None,
        }

    best_agent = "summary"
    best_score = 0
    for atype, ameta in AGENT_ROLE_META.items():
        if atype == agent_type:
            continue
        s = sum(1 for kw in ameta["keywords"] if kw in task_l)
        if s > best_score:
            best_score = s
            best_agent = atype

    if best_score >= 1:
        return {
            "matches": False,
            "score": score,
            "reason": (
                f"Cette tâche correspond plutôt au **{AGENT_LABELS.get(best_agent, best_agent)}**, "
                f"pas au {AGENT_LABELS.get(agent_type, agent_type)}."
            ),
            "suggested_agent": best_agent,
        }

    return {
        "matches": False,
        "score": 0,
        "reason": (
            f"Le {AGENT_LABELS.get(agent_type, agent_type)} ne traite pas ce type de demande. "
            "Choisissez un autre agent ou reformulez la tâche."
        ),
        "suggested_agent": "summary",
    }


def _build_mission_schema(mission: AgentMission, role_check: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = AGENT_ROLE_META.get(mission.agent_type, AGENT_ROLE_META["summary"])
    schedule_label = {
        "now": "Lancement immédiat",
        "datetime": "Date/heure planifiée",
        "daily": "Quotidien",
        "weekly": "Hebdomadaire",
    }.get(mission.schedule_type, mission.schedule_type)

    rc = role_check or _assess_task_role(mission.task_description, mission.agent_type)
    return {
        "version": 2,
        "type": "workflow",
        "trigger": {"id": "trigger", "label": schedule_label, "description": "Déclencheur admin"},
        "agent": {
            "id": mission.agent_type,
            "label": AGENT_LABELS.get(mission.agent_type, mission.agent_type),
            "description": "Agent IA avec outils métier",
        },
        "tools": [{"id": f"tool_{i}", "label": t} for i, t in enumerate(meta["tools"])],
        "decision": {
            "id": "role_check",
            "label": "Tâche dans le rôle de l'agent ?",
            "yes_label": "Oui → exécuter et répondre",
            "no_label": "Non → informer l'admin",
            "matches": rc.get("matches"),
            "reason": rc.get("reason", ""),
            "suggested_agent": rc.get("suggested_agent"),
        },
        "outcomes": {
            "success": {"label": "Résultat livré", "description": "Réponse à votre tâche"},
            "rejected": {
                "label": "Hors rôle",
                "description": "Agent recommandé indiqué",
            },
        },
        "task": mission.task_description,
    }


def _safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _save_mission_schema(mission: AgentMission, role_check: dict[str, Any] | None = None) -> None:
    mission.plan_json = _safe_json_dumps(_build_mission_schema(mission, role_check))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(
    db: Session,
    mission: AgentMission,
    message: str,
    *,
    level: str = "info",
    step_id: int | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AgentExecutionLog(
            mission_id=mission.id,
            step_id=step_id,
            level=level,
            message=message,
            details_json=_safe_json_dumps(details or {}),
        )
    )


def _append_mission_message(
    db: Session,
    mission_id: int,
    sender: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AgentMissionMessage(
            mission_id=mission_id,
            sender=sender,
            content=content.strip(),
            metadata_json=_safe_json_dumps(metadata or {}),
        )
    )


def _notify_mission_lifecycle(
    db: Session,
    mission: AgentMission,
    phase: str,
    *,
    summary: str = "",
) -> None:
    if phase == "start" and not getattr(mission, "notify_on_start", True):
        return
    if phase == "complete" and not getattr(mission, "notify_on_complete", True):
        return
    label = AGENT_LABELS.get(mission.agent_type, mission.agent_type)
    if phase == "start":
        title = f"Mission agent démarrée — {label}"
        body = (mission.task_description or "")[:400]
    else:
        title = f"Mission agent terminée — {label}"
        body = summary[:500] or (mission.task_description or "")[:400]
    upsert_platform_notification(
        db,
        external_key=f"agent-mission-{mission.id}-{phase}",
        category="agent_mission",
        title=title,
        message=body,
        route=f"/admin/agent-missions/{mission.id}?tab=results",
        icon="cpu",
        action_label="Voir résultats",
        action_type="agent_mission",
        action_ref=str(mission.id),
        priority="normal",
    )


def _record_mission_conversation(
    db: Session,
    mission: AgentMission,
    task: str,
    output: dict[str, Any],
) -> None:
    if task.strip():
        _append_mission_message(db, mission.id, "admin", task.strip())
    answer = str(output.get("task_answer") or output.get("analysis") or "").strip()
    if answer:
        _append_mission_message(
            db,
            mission.id,
            "agent",
            answer,
            {
                "agent_steps": output.get("agent_steps"),
                "agent_reasoning": output.get("agent_reasoning"),
                "action_executed": output.get("action_executed"),
                "needs_approval": output.get("needs_approval"),
                "analysis_only": output.get("analysis_only"),
            },
        )


def _enrich_mission_context(db: Session, mission: AgentMission, context: dict[str, Any]) -> dict[str, Any]:
    if mission.agent_type == "tracking":
        numbers = extract_tracking_numbers(mission.task_description)
        if numbers:
            rows = admin_find_tracking_rows(db, numbers)
            found = {r.tracking_number for r in rows}
            context["requested_trackings"] = [
                {
                    "tracking_number": r.tracking_number,
                    "status": str(r.status or ""),
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
            context["missing_trackings"] = [n for n in numbers if n not in found]
    if mission.agent_type in ("logs", "summary"):
        context.setdefault(
            "behavior",
            aggregate_user_behavior(db, hours=24, limit_users=mission.max_items),
        )
    if mission.agent_type == "support":
        ticket = find_ticket_for_task(db, mission.task_description)
        if ticket:
            context["target_ticket"] = ticket_context_dict(ticket)
    return context


def _latest_agent_ui(mission: AgentMission) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    for step in reversed(sorted(mission.steps or [], key=lambda s: s.step_order)):
        output = _parse_step_output(step.output_json)
        if output.get("agent_steps") or output.get("agent_reasoning"):
            steps = output.get("agent_steps") if isinstance(output.get("agent_steps"), list) else []
            reasoning = output.get("agent_reasoning") if isinstance(output.get("agent_reasoning"), dict) else None
            return steps, reasoning
    return [], None


def _mission_read(mission: AgentMission) -> AgentMissionRead:
    pending = [a for a in (mission.approvals or []) if a.status == "pending"]
    return AgentMissionRead(
        id=mission.id,
        admin_id=mission.admin_id,
        agent_type=mission.agent_type,
        task_description=mission.task_description,
        status=mission.status,
        schedule_type=mission.schedule_type,
        scheduled_at=mission.scheduled_at,
        schedule_time=mission.schedule_time,
        max_items=mission.max_items,
        max_duration_minutes=mission.max_duration_minutes,
        require_approval_sensitive=mission.require_approval_sensitive,
        notify_on_start=getattr(mission, "notify_on_start", True),
        notify_on_complete=getattr(mission, "notify_on_complete", True),
        plan_json=mission.plan_json,
        created_at=mission.created_at,
        updated_at=mission.updated_at,
        started_at=mission.started_at,
        finished_at=mission.finished_at,
        cancelled_at=mission.cancelled_at,
        steps=[AgentMissionStepRead.model_validate(s) for s in sorted(mission.steps, key=lambda x: x.step_order)],
        pending_approvals=[AgentApprovalRead.model_validate(a) for a in pending],
    )


def _parse_step_output(output_json: str) -> dict[str, Any]:
    if not output_json or output_json.strip() in ("", "{}"):
        return {}
    try:
        data = json.loads(output_json)
        return data if isinstance(data, dict) else {"value": data}
    except json.JSONDecodeError:
        return {"raw": output_json}


def _build_mission_results(mission: AgentMission) -> AgentMissionResults:
    step_results: list[AgentStepResultRead] = []
    metrics: dict[str, Any] = {}
    executive_summary = ""

    for step in sorted(mission.steps or [], key=lambda s: s.step_order):
        output = _parse_step_output(step.output_json)
        if step.status not in ("completed", "skipped", "waiting_approval") or not output:
            continue
        step_results.append(
            AgentStepResultRead(
                step_id=step.id,
                step_order=step.step_order,
                title=step.title,
                action_type=step.action_type,
                status=step.status,
                output=output,
            )
        )
        if "summary" in output and isinstance(output["summary"], str):
            executive_summary = output["summary"]
        for key, value in output.items():
            if key in (
                "action",
                "simulated",
                "note",
                "task",
                "analysis",
                "raw",
                "value",
                "summary",
                "task_answer",
                "findings",
                "recommendations",
                "sample_logs",
                "sample_tickets",
                "sample_users",
            ):
                continue
            if isinstance(value, (int, float, str, bool)):
                metrics[key] = value

    if not executive_summary and step_results:
        for step in reversed(step_results):
            answer = step.output.get("task_answer") or step.output.get("analysis")
            if isinstance(answer, str) and answer.strip():
                executive_summary = answer.strip()
                break
        if not executive_summary:
            last = step_results[-1].output
            executive_summary = str(last.get("summary") or last.get("analysis") or last.get("note") or "")

    if not executive_summary and step_results:
        executive_summary = f"{len(step_results)} étape(s) exécutée(s) — consultez le détail ci-dessous."

    preview = executive_summary[:120] if executive_summary else ""
    return AgentMissionResults(
        has_results=bool(step_results),
        executive_summary=executive_summary,
        metrics=metrics,
        step_results=step_results,
    )


def _list_item_from_mission(mission: AgentMission) -> AgentMissionListItem:
    results = _build_mission_results(mission)
    return AgentMissionListItem(
        id=mission.id,
        agent_type=mission.agent_type,
        task_description=mission.task_description,
        status=mission.status,
        schedule_type=mission.schedule_type,
        scheduled_at=mission.scheduled_at,
        created_at=mission.created_at,
        started_at=mission.started_at,
        finished_at=mission.finished_at,
        has_results=results.has_results,
        result_preview=results.executive_summary[:160],
    )


def list_missions(db: Session) -> AgentMissionListResponse:
    rows = list(
        db.scalars(
            select(AgentMission)
            .options(joinedload(AgentMission.steps))
            .order_by(AgentMission.created_at.desc())
        )
        .unique()
        .all()
    )
    rows = [r for r in rows if '"type": "copilot"' not in (r.plan_json or "") and '"type":"copilot"' not in (r.plan_json or "")]
    items = [_list_item_from_mission(r) for r in rows]
    stats = {
        "total": len(rows),
        "waiting_plan_approval": sum(1 for r in rows if r.status in ("draft", "waiting_plan_approval")),
        "running": sum(1 for r in rows if r.status in ("running", "waiting_permission")),
        "completed": sum(1 for r in rows if r.status == "completed"),
    }
    return AgentMissionListResponse(items=items, total=len(items), stats=stats)


def get_mission(db: Session, mission_id: int) -> AgentMissionDetailResponse | None:
    mission = db.scalar(
        select(AgentMission)
        .options(
            joinedload(AgentMission.steps),
            joinedload(AgentMission.approvals),
            joinedload(AgentMission.logs),
            joinedload(AgentMission.messages),
        )
        .where(AgentMission.id == mission_id)
    )
    if not mission:
        return None
    base = _mission_read(mission)
    logs = sorted(mission.logs, key=lambda x: x.created_at)
    messages = sorted(mission.messages, key=lambda x: x.created_at)
    results = _build_mission_results(mission)
    agent_steps, agent_reasoning = _latest_agent_ui(mission)
    return AgentMissionDetailResponse(
        **base.model_dump(),
        logs=[AgentExecutionLogRead.model_validate(l) for l in logs],
        messages=[AgentMissionMessageRead.model_validate(m) for m in messages],
        agent_steps=agent_steps,
        agent_reasoning=agent_reasoning,
        results=results,
    )


def create_mission(db: Session, admin: User, payload: AgentMissionCreate) -> AgentMissionRead:
    row = AgentMission(
        admin_id=admin.id,
        agent_type=payload.agent_type,
        task_description=payload.task_description.strip(),
        status="draft",
        schedule_type=payload.schedule_type,
        scheduled_at=payload.scheduled_at,
        schedule_time=payload.schedule_time,
        max_items=payload.max_items,
        max_duration_minutes=payload.max_duration_minutes,
        require_approval_sensitive=payload.require_approval_sensitive,
        notify_on_start=payload.notify_on_start,
        notify_on_complete=payload.notify_on_complete,
    )
    db.add(row)
    db.flush()
    if payload.plan_json and _parse_workflow_builder(payload.plan_json):
        row.plan_json = payload.plan_json
    else:
        _save_mission_schema(row)
    _log(db, row, f"Mission créée — {AGENT_LABELS.get(payload.agent_type, payload.agent_type)}")
    db.commit()
    db.refresh(row)
    return _mission_read(row)


def update_mission_workflow(
    db: Session, mission_id: int, payload: AgentMissionWorkflowUpdate
) -> AgentMissionRead:
    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals)).where(
            AgentMission.id == mission_id
        )
    )
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    if mission.status in ("running", "completed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mission non modifiable dans cet état")

    if not _parse_workflow_builder(payload.plan_json):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow invalide")

    mission.agent_type = payload.agent_type
    mission.task_description = payload.task_description.strip()
    mission.schedule_type = payload.schedule_type
    mission.scheduled_at = payload.scheduled_at
    mission.schedule_time = payload.schedule_time
    mission.max_items = payload.max_items
    mission.max_duration_minutes = payload.max_duration_minutes
    mission.require_approval_sensitive = payload.require_approval_sensitive
    mission.notify_on_start = payload.notify_on_start
    mission.notify_on_complete = payload.notify_on_complete
    mission.plan_json = payload.plan_json
    mission.updated_at = _now()
    _log(db, mission, "Workflow orchestrateur mis à jour")
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def generate_plan(db: Session, mission_id: int) -> AgentMissionRead:
    """Régénère le schéma visuel (workflow) — pas de plan multi-étapes."""
    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps)).where(AgentMission.id == mission_id)
    )
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    if mission.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mission annulée")

    _save_mission_schema(mission)
    mission.updated_at = _now()
    _log(db, mission, "Schéma workflow mis à jour")
    db.commit()
    db.refresh(mission)
    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals)).where(
            AgentMission.id == mission_id
        )
    )
    return _mission_read(mission)  # type: ignore[arg-type]


def approve_plan(db: Session, mission_id: int) -> AgentMissionRead:
    """Compatibilité API — le schéma ne nécessite plus de validation."""
    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals)).where(
            AgentMission.id == mission_id
        )
    )
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")

    if mission.status == "waiting_plan_approval":
        mission.status = "draft"
        _log(db, mission, "Schéma prêt — lancez la mission")
    mission.updated_at = _now()
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def cancel_mission(db: Session, mission_id: int) -> AgentMissionRead:
    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals)).where(
            AgentMission.id == mission_id
        )
    )
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    if mission.status in ("completed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mission déjà terminée ou annulée")

    mission.status = "cancelled"
    mission.cancelled_at = _now()
    mission.updated_at = _now()
    _log(db, mission, "Mission annulée par l'administrateur", level="warning")
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def _gather_mission_context(db: Session, mission: AgentMission) -> dict[str, Any]:
    """Collecte les données réelles liées à la tâche admin."""
    limit = mission.max_items
    ctx: dict[str, Any] = {
        "task": mission.task_description,
        "agent_type": mission.agent_type,
    }
    try:
        recent_logs = list(
            db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)).all()
        )
        ctx["logs_total"] = db.scalar(select(func.count()).select_from(ActivityLog)) or 0
        ctx["logs_sample"] = [
            {
                "level": str(row.level or ""),
                "category": str(row.category or ""),
                "action": str(row.action or ""),
                "message": (row.message or "")[:240],
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in recent_logs
        ]

        security_logs = list(
            db.scalars(
                select(ActivityLog)
                .where(
                    or_(
                        ActivityLog.category == "security",
                        ActivityLog.level.in_(("WARNING", "CRITICAL")),
                        ActivityLog.action.like("security.%"),
                    )
                )
                .order_by(ActivityLog.created_at.desc())
                .limit(limit)
            ).all()
        )
        ctx["security_logs_sample"] = [
            {
                "level": str(row.level or ""),
                "action": str(row.action or ""),
                "message": (row.message or "")[:240],
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in security_logs
        ]

        open_incidents = list(
            db.scalars(
                select(SecurityIncident)
                .where(SecurityIncident.status.in_(("open", "acknowledged")))
                .order_by(SecurityIncident.created_at.desc())
                .limit(limit)
            ).all()
        )
        ctx["security_incidents_open"] = db.scalar(
            select(func.count())
            .select_from(SecurityIncident)
            .where(SecurityIncident.status.in_(("open", "acknowledged")))
        ) or 0
        ctx["security_incidents_sample"] = [
            {
                "id": inc.id,
                "severity": str(inc.severity or ""),
                "title": inc.title,
                "summary": (inc.summary or "")[:200],
                "threat_type": str(inc.threat_type or ""),
                "created_at": inc.created_at.isoformat() if inc.created_at else "",
            }
            for inc in open_incidents
        ]

        open_tickets = list(
            db.scalars(
                select(SupportTicket)
                .where(SupportTicket.status.in_((SupportTicketStatus.open, SupportTicketStatus.pending)))
                .order_by(SupportTicket.created_at.desc())
                .limit(limit)
            ).all()
        )
        ctx["open_tickets_count"] = db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status.in_((SupportTicketStatus.open, SupportTicketStatus.pending)))
        ) or 0
        ctx["tickets_sample"] = [
            {
                "id": t.id,
                "subject": t.subject,
                "priority": str(t.priority or ""),
                "status": str(t.status or ""),
                "message": (t.message or "")[:200],
            }
            for t in open_tickets
        ]

        users = list(db.scalars(select(User).order_by(User.created_at.desc()).limit(limit)).all())
        ctx["users_total"] = db.scalar(select(func.count()).select_from(User)) or 0
        ctx["users_sample"] = [
            {
                "id": u.id,
                "email": u.email,
                "role": str(u.role or ""),
                "status": str(u.status or ""),
                "full_name": u.full_name,
            }
            for u in users
        ]
        ctx["users_suspended"] = db.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.suspended.value)
        ) or 0

        trackings = list(
            db.scalars(select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(limit)).all()
        )
        ctx["trackings_sample"] = [
            {
                "tracking_number": t.tracking_number,
                "status": str(t.status or ""),
                "created_at": t.created_at.isoformat() if t.created_at else "",
            }
            for t in trackings
        ]

        notifs = list(
            db.scalars(select(PlatformNotification).order_by(PlatformNotification.created_at.desc()).limit(limit)).all()
        )
        ctx["notifications_total"] = db.scalar(select(func.count()).select_from(PlatformNotification)) or 0
        ctx["notifications_unread"] = db.scalar(
            select(func.count()).select_from(PlatformNotification).where(PlatformNotification.is_read.is_(False))
        ) or 0
        ctx["notifications_sample"] = [
            {
                "title": n.title,
                "category": str(n.category or ""),
                "priority": str(n.priority or ""),
                "is_read": bool(n.is_read),
                "message": (n.message or "")[:180],
            }
            for n in notifs
        ]
        attack_related = [
            n
            for n in notifs
            if any(
                kw in f"{n.title} {n.message} {n.category}".lower()
                for kw in ("attack", "attaque", "security", "sécurité", "incident", "ids", "suspicious")
            )
        ]
        ctx["attack_related_notifications"] = len(attack_related)
    except Exception as exc:
        logger.exception("Contexte mission partiel (mission #%s): %s", mission.id, exc)
        ctx["context_error"] = str(exc)[:300]

    return ctx


def _mission_llm_analyze(mission: AgentMission, step: AgentMissionStep, context: dict[str, Any]) -> str:
    """Analyse IA centrée sur la tâche demandée par l'admin."""
    from app.core.config import get_settings
    from app.services.llm.providers import LlmProviderError, _gemini_generate

    settings = get_settings()
    if not settings.llm_enabled:
        return ""

    try:
        context_json = _safe_json_dumps(context)[:9000]
        prompt = (
            f"TÂCHE EXACTE DE L'ADMINISTRATEUR:\n{mission.task_description}\n\n"
            f"ÉTAPE EN COURS: {step.title} ({step.action_type})\n"
            f"AGENT: {AGENT_LABELS.get(mission.agent_type, mission.agent_type)}\n\n"
            f"DONNÉES RÉELLES (JSON):\n{context_json}"
        )
        return _gemini_generate(
            prompt,
            max_output_tokens=1024,
            system_instruction=ADMIN_MISSION_SYSTEM_PROMPT,
            ui_language="fr",
        ).strip()
    except LlmProviderError as exc:
        logger.warning("Mission #%s étape %s — LLM indisponible: %s", mission.id, step.id, exc)
        return ""
    except Exception as exc:
        logger.exception("Mission #%s étape %s — erreur LLM: %s", mission.id, step.id, exc)
        return ""


def _fallback_task_answer(mission: AgentMission, step: AgentMissionStep, context: dict[str, Any]) -> str:
    """Réponse déterministe si le LLM est indisponible."""
    task = mission.task_description[:120]
    if step.action_type == "read_logs":
        n = len(context.get("logs_sample", []))
        return f"Analyse logs pour: « {task} » — {n} entrées récentes examinées sur {context.get('logs_total', 0)} au total."
    if step.action_type == "analyze_tickets":
        return (
            f"Analyse support pour: « {task} » — {context.get('open_tickets_count', 0)} ticket(s) ouvert(s), "
            f"{len(context.get('tickets_sample', []))} analysé(s) en détail."
        )
    if step.action_type == "analyze_users":
        return (
            f"Analyse utilisateurs pour: « {task} » — {context.get('users_total', 0)} comptes, "
            f"{context.get('users_suspended', 0)} suspendu(s)."
        )
    if step.action_type == "analyze_notifications":
        return (
            f"Analyse notifications pour: « {task} » — {context.get('notifications_total', 0)} notification(s), "
            f"{context.get('notifications_unread', 0)} non lue(s), "
            f"{context.get('attack_related_notifications', 0)} liée(s) à la sécurité, "
            f"{context.get('security_incidents_open', 0)} incident(s) sécurité ouvert(s)."
        )
    if step.action_type == "generate_summary":
        return f"Synthèse mission: « {task} » — données logs, tickets et utilisateurs agrégées."
    return f"Traitement de l'étape « {step.title} » pour la mission: {task}"


def _execute_step_tool(db: Session, mission: AgentMission, step: AgentMissionStep) -> dict[str, Any]:
    """Exécute une étape : données réelles + analyse IA sur la tâche admin."""
    action = step.action_type
    context = _gather_mission_context(db, mission)
    output: dict[str, Any] = {
        "action": action,
        "task": mission.task_description,
    }

    if action == "read_logs":
        sample = context.get("logs_sample", [])
        levels: dict[str, int] = {}
        for row in sample:
            levels[row["level"]] = levels.get(row["level"], 0) + 1
        output.update(
            {
                "total_logs": context.get("logs_total", 0),
                "sample_count": len(sample),
                "levels": levels,
                "sample_logs": sample[:5],
            }
        )

    elif action == "analyze_logs":
        warnings = db.scalar(
            select(func.count()).select_from(ActivityLog).where(ActivityLog.level.in_(("WARNING", "CRITICAL")))
        ) or 0
        output["warning_critical_count"] = warnings

    elif action == "analyze_tickets":
        output["open_tickets"] = context.get("open_tickets_count", 0)
        output["sample_tickets"] = context.get("tickets_sample", [])[:5]

    elif action == "analyze_users":
        output["total_users"] = context.get("users_total", 0)
        output["users_suspended"] = context.get("users_suspended", 0)
        output["sample_users"] = context.get("users_sample", [])[:5]

    elif action == "analyze_tracking":
        sample = context.get("trackings_sample", [])
        output["shipments_reviewed"] = len(sample)
        output["trackings_sample"] = sample[:5]

    elif action == "analyze_notifications":
        sample = context.get("notifications_sample", [])
        output["notifications_total"] = context.get("notifications_total", 0)
        output["notifications_unread"] = context.get("notifications_unread", 0)
        output["notifications_reviewed"] = len(sample)
        output["attack_related_notifications"] = context.get("attack_related_notifications", 0)
        output["security_incidents_open"] = context.get("security_incidents_open", 0)
        output["notifications_sample"] = sample[:5]
        output["security_incidents_sample"] = context.get("security_incidents_sample", [])[:5]

    elif action in ("draft_support_reply", "draft_user_actions", "draft_notification"):
        output["drafts_prepared"] = min(3, mission.max_items)
        output["status"] = "ready_for_review"

    elif action in SENSITIVE_ACTIONS:
        output.update(
            {
                "executed": True,
                "note": "Action sensible simulée — aucune modification réelle sans intégration métier complète.",
            }
        )

    # Analyse IA (ou fallback) pour répondre à la tâche demandée
    if action not in SENSITIVE_ACTIONS:
        task_answer = _mission_llm_analyze(mission, step, context)
        if not task_answer:
            task_answer = _fallback_task_answer(mission, step, context)
        output["task_answer"] = task_answer
        if action == "generate_summary":
            output["summary"] = task_answer
        else:
            output["analysis"] = task_answer

    return output


def _create_approval(db: Session, mission: AgentMission, step: AgentMissionStep) -> AgentApprovalRequest:
    payload = {
        "mission_id": mission.id,
        "step_id": step.id,
        "action_type": step.action_type,
        "max_items": mission.max_items,
    }
    approval = AgentApprovalRequest(
        mission_id=mission.id,
        step_id=step.id,
        action_type=step.action_type,
        description=f"Autoriser : {step.title}",
        payload_json=json.dumps(payload, ensure_ascii=False),
        status="pending",
    )
    db.add(approval)
    step.status = "waiting_approval"
    mission.status = "waiting_permission"
    _log(db, mission, f"Approbation requise — {step.title}", level="warning", step_id=step.id)
    return approval


def _execute_direct_mission(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    actor_admin_id: int,
    approved: bool = False,
) -> dict[str, Any]:
    """Exécution via runtime unifié (outils + cerveau Gemini)."""
    context = _enrich_mission_context(db, mission, _gather_mission_context(db, mission))
    return execute_admin_mission_task(
        db,
        mission,
        step,
        task=mission.task_description,
        actor_admin_id=actor_admin_id,
        require_approval=mission.require_approval_sensitive,
        approved=approved,
        context=context,
    )


def _handle_step_output(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    output: dict[str, Any],
) -> None:
    """Applique le résultat d'une étape : approbation, statuts honnêtes."""
    if output.get("needs_approval") and output.get("approval_payload"):
        payload = dict(output["approval_payload"])
        payload["mission_id"] = mission.id
        payload["step_id"] = step.id
        approval = AgentApprovalRequest(
            mission_id=mission.id,
            step_id=step.id,
            action_type=payload.get("action_type", step.action_type),
            description=f"Autoriser : {payload.get('action_type', step.action_type)} — {payload.get('email', '')}",
            payload_json=_safe_json_dumps(payload),
            status="pending",
        )
        db.add(approval)
        step.status = "waiting_approval"
        step.output_json = _safe_json_dumps(output)
        step.finished_at = None
        mission.status = "waiting_permission"
        _log(db, mission, f"Approbation requise — {approval.description}", level="warning", step_id=step.id)
        return

    step.output_json = _safe_json_dumps(output)
    step.status = "completed"
    step.finished_at = _now()
    if output.get("error") and not output.get("action_executed"):
        _log(db, mission, f"Étape terminée sans action — {output.get('error')}", level="warning", step_id=step.id)
    elif output.get("action_executed"):
        _log(db, mission, "Action exécutée et vérifiée", step_id=step.id, details=output.get("verification"))
    else:
        _log(db, mission, "Analyse terminée", step_id=step.id)


def _role_mismatch_output(mission: AgentMission, role: dict[str, Any]) -> dict[str, Any]:
    suggested = role.get("suggested_agent")
    suggested_label = AGENT_LABELS.get(suggested, suggested) if suggested else "Summary Agent"
    msg = (
        f"Ce n'est pas le rôle du {AGENT_LABELS.get(mission.agent_type, mission.agent_type)}.\n\n"
        f"{role.get('reason', '')}\n\n"
        f"Agent recommandé : **{suggested_label}**\n\n"
        "Créez une nouvelle mission avec le bon agent ou reformulez votre demande."
    )
    return {
        "role_mismatch": True,
        "task_answer": msg,
        "analysis": msg,
        "suggested_agent": suggested,
        "suggested_agent_label": suggested_label,
    }


def _reset_failed_mission(mission: AgentMission) -> None:
    mission.status = "draft"
    mission.finished_at = None
    for step in mission.steps:
        if step.status in ("failed", "running"):
            step.status = "pending"
            step.output_json = "{}"
            step.started_at = None
            step.finished_at = None


def run_mission(db: Session, mission_id: int) -> AgentMissionRead:
    """Exécution selon le workflow builder (multi-tâches) ou mode direct."""
    mission = db.scalar(
        select(AgentMission)
        .options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals))
        .where(AgentMission.id == mission_id)
    )
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    if mission.status in ("cancelled", "completed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mission terminée ou annulée")
    if mission.status == "failed":
        _reset_failed_mission(mission)
        _log(db, mission, "Mission réinitialisée après échec — nouvelle exécution")
        db.flush()

    actor_admin_id = mission.admin_id
    wf = _parse_workflow_builder(mission.plan_json)
    is_first_start = mission.started_at is None

    if mission.status != "waiting_permission":
        for step in list(mission.steps):
            db.delete(step)
        db.flush()

    mission.status = "running"
    if not mission.started_at:
        mission.started_at = _now()
    mission.updated_at = _now()
    _log(db, mission, "Exécution démarrée (orchestrateur)")
    if is_first_start:
        _notify_mission_lifecycle(db, mission, "start")
    db.flush()

    mission_completed = True
    completion_summary = ""

    try:
        if wf:
            task_nodes = _workflow_ordered_tasks(wf)
            if not task_nodes:
                raise ValueError("Aucune tâche reliée dans le workflow")
            outputs_dest = _workflow_output_destinations(wf)
            for idx, task_node in enumerate(task_nodes, start=1):
                task_text = (task_node.get("data") or {}).get("description", "").strip()
                task_label = (task_node.get("data") or {}).get("label", f"Tâche {idx}")
                role = _assess_task_role(task_text, mission.agent_type)

                step = AgentMissionStep(
                    mission_id=mission.id,
                    step_order=idx,
                    title=task_label,
                    description=task_text[:500],
                    action_type=AGENT_ROLE_META.get(mission.agent_type, AGENT_ROLE_META["summary"])["action"],
                    is_sensitive=False,
                    status="running",
                    started_at=_now(),
                )
                db.add(step)
                db.flush()
                _log(db, mission, f"Tâche {idx} — {task_label}", step_id=step.id)

                if not role["matches"]:
                    output = _role_mismatch_output(mission, role)
                    _log(db, mission, "Hors rôle", level="warning", step_id=step.id)
                    step.output_json = _safe_json_dumps(output)
                    step.status = "completed"
                    step.finished_at = _now()
                    _record_mission_conversation(db, mission, task_text, output)
                    completion_summary = str(output.get("task_answer") or "")
                else:
                    saved_task = mission.task_description
                    mission.task_description = task_text
                    output = _execute_direct_mission(
                        db, mission, step, actor_admin_id=actor_admin_id
                    )
                    mission.task_description = saved_task
                    output["workflow_node_id"] = task_node.get("id")
                    if outputs_dest:
                        output["output_destinations"] = outputs_dest
                    _handle_step_output(db, mission, step, output)
                    _record_mission_conversation(db, mission, task_text, output)
                    completion_summary = str(output.get("task_answer") or completion_summary)
                    if step.status == "waiting_approval":
                        mission_completed = False
                        break

            if mission_completed:
                mission.status = "completed"
                mission.finished_at = _now()
                _log(db, mission, f"Workflow terminé — {len(task_nodes)} tâche(s)")
        else:
            role = _assess_task_role(mission.task_description, mission.agent_type)
            _save_mission_schema(mission, role)

            step = AgentMissionStep(
                mission_id=mission.id,
                step_order=1,
                title="Exécuter la mission",
                description=mission.task_description[:500],
                action_type=AGENT_ROLE_META.get(mission.agent_type, AGENT_ROLE_META["summary"])["action"],
                is_sensitive=False,
                status="running",
                started_at=_now(),
            )
            db.add(step)
            db.flush()
            _log(db, mission, f"Agent {AGENT_LABELS.get(mission.agent_type, mission.agent_type)}", step_id=step.id)

            if not role["matches"]:
                output = _role_mismatch_output(mission, role)
                _log(db, mission, "Tâche hors rôle", level="warning", step_id=step.id)
                step.output_json = _safe_json_dumps(output)
                step.status = "completed"
                step.finished_at = _now()
                mission.status = "completed"
                mission.finished_at = _now()
                _record_mission_conversation(db, mission, mission.task_description, output)
                completion_summary = str(output.get("task_answer") or "")
            else:
                output = _execute_direct_mission(
                    db, mission, step, actor_admin_id=actor_admin_id
                )
                _handle_step_output(db, mission, step, output)
                _record_mission_conversation(db, mission, mission.task_description, output)
                completion_summary = str(output.get("task_answer") or "")
                if step.status == "waiting_approval":
                    mission_completed = False
                elif step.status == "completed":
                    mission.status = "completed"
                    mission.finished_at = _now()
                    _save_mission_schema(mission, {**role, "matches": role["matches"]})
                    _log(db, mission, "Mission terminée")

        mission.updated_at = _now()
        if mission.status == "completed":
            if not completion_summary:
                completion_summary = _build_mission_results(mission).executive_summary
            _notify_mission_lifecycle(db, mission, "complete", summary=completion_summary)
    except Exception as exc:
        logger.exception("Échec mission #%s", mission.id)
        mission.status = "failed"
        mission.finished_at = _now()
        _log(db, mission, f"Échec : {exc}", level="error")

    db.commit()
    mission = db.scalar(
        select(AgentMission)
        .options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals))
        .where(AgentMission.id == mission_id)
    )
    return _mission_read(mission)  # type: ignore[arg-type]


def get_mission_logs(db: Session, mission_id: int) -> list[AgentExecutionLogRead]:
    mission = db.scalar(select(AgentMission).where(AgentMission.id == mission_id))
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    rows = list(
        db.scalars(
            select(AgentExecutionLog)
            .where(AgentExecutionLog.mission_id == mission_id)
            .order_by(AgentExecutionLog.created_at)
        ).all()
    )
    return [AgentExecutionLogRead.model_validate(r) for r in rows]


def approve_request(db: Session, approval_id: int, admin: User) -> tuple[AgentApprovalRequest, AgentMissionRead]:
    approval = db.scalar(select(AgentApprovalRequest).where(AgentApprovalRequest.id == approval_id))
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Demande déjà traitée")

    approval.status = "approved"
    approval.resolved_by_admin_id = admin.id
    approval.resolved_at = _now()

    step = db.scalar(select(AgentMissionStep).where(AgentMissionStep.id == approval.step_id))
    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals)).where(
            AgentMission.id == approval.mission_id
        )
    )
    if not mission or not step:
        db.commit()
        db.refresh(approval)
        return approval, _mission_read(mission)  # type: ignore[arg-type]

    _log(db, mission, f"Approbation accordée — {approval.description}", step_id=approval.step_id)

    try:
        payload = json.loads(approval.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}

    tool_args = payload.get("args") if isinstance(payload.get("args"), dict) else {}

    action_type = payload.get("action_type", approval.action_type)
    if action_type == "send_email_with_attachment" and payload.get("email_to"):
        output = execute_approved_email_attachment(
            db,
            email_to=str(payload["email_to"]),
            tracking_numbers=[str(n) for n in (payload.get("tracking_numbers") or [])],
            mission_id=mission.id,
        )
        step.output_json = _safe_json_dumps(output)
        step.status = "completed"
        step.finished_at = _now()
        mission.status = "completed"
        mission.finished_at = _now()
        mission.updated_at = _now()
        _log(db, mission, "E-mail envoyé après approbation", step_id=step.id)
        _record_mission_conversation(db, mission, mission.task_description, output)
        _notify_mission_lifecycle(db, mission, "complete", summary=str(output.get("task_answer") or ""))
    elif action_type == "reply_support_ticket" and payload.get("ticket_id") and payload.get("reply_body"):
        output = execute_approved_support_reply(
            db,
            ticket_id=int(payload["ticket_id"]),
            reply_body=str(payload["reply_body"]),
            admin_id=admin.id,
            mission_id=mission.id,
        )
        step.output_json = _safe_json_dumps(output)
        step.status = "completed"
        step.finished_at = _now()
        mission.status = "completed"
        mission.finished_at = _now()
        mission.updated_at = _now()
        _log(db, mission, "Réponse support publiée après approbation", step_id=step.id)
        _record_mission_conversation(db, mission, mission.task_description, output)
        _notify_mission_lifecycle(db, mission, "complete", summary=str(output.get("task_answer") or ""))
    elif action_type in ("reactivate_all_suspended", "suspend_all_active") and payload.get("user_ids"):
        output = execute_approved_bulk_users(
            db,
            action_type=action_type,
            user_ids=[int(x) for x in payload["user_ids"]],
            admin_id=admin.id,
            mission_id=mission.id,
            reason=str(payload.get("reason") or ""),
        )
        step.output_json = _safe_json_dumps(output)
        step.status = "completed"
        step.finished_at = _now()
        mission.status = "completed"
        mission.finished_at = _now()
        mission.updated_at = _now()
        _log(db, mission, "Action en lot exécutée après approbation", step_id=step.id)
        _record_mission_conversation(db, mission, mission.task_description, output)
        _notify_mission_lifecycle(db, mission, "complete", summary=str(output.get("task_answer") or ""))
    elif action_type in ("suspend_user", "reactivate_user"):
        uid = payload.get("user_id") or tool_args.get("user_id")
        email = payload.get("email") or tool_args.get("email")
        user = db.get(User, int(uid)) if uid else None
        if user is None and email:
            user = db.scalar(select(User).where(User.email == str(email).strip()))
        if user:
            reason = str(payload.get("reason") or f"Approuvé par admin #{admin.id}")
            ok, verification = _execute_user_sensitive_action(
                db,
                action_type=action_type,
                user=user,
                actor_admin_id=admin.id,
                reason=reason,
            )
            label = "suspendu" if action_type == "suspend_user" else "réactivé"
            output = {
                "action": action_type,
                "action_executed": ok,
                "needs_approval": False,
                "verification": verification,
                "task_answer": (
                    f"FAIT — Compte {user.email} (#{user.id}) {label} après approbation.\n"
                    f"Vérification : {verification['status_before']} → {verification['status_after']}"
                    if ok
                    else f"NON FAIT — Échec après approbation pour {user.email}."
                ),
            }
            step.output_json = _safe_json_dumps(output)
            step.status = "completed"
            step.finished_at = _now()
            mission.status = "completed"
            mission.finished_at = _now()
            mission.updated_at = _now()
            _log(db, mission, "Action sensible exécutée après approbation", step_id=step.id)
            _record_mission_conversation(db, mission, mission.task_description, output)
            _notify_mission_lifecycle(db, mission, "complete", summary=str(output.get("task_answer") or ""))
        else:
            step.status = "failed"
            step.finished_at = _now()
            mission.status = "failed"
            mission.finished_at = _now()
    elif action_type in (
        "send_email",
        "send_client_email",
        "notify_user",
        "notify_user_warning",
        "notify_employee",
        "reply_support_ticket",
        "send_notification",
        "close_ticket",
        "escalate_ticket",
        "notify_users_by_role",
        "notify_all_users",
        "send_bulk_email",
        "suspend_users_bulk",
    ):
        from app.services.ai_assistant.tool_executor import build_tool_context
        from app.services.gpt.tool_executor import execute_tool
        from app.services.gpt.tool_types import ToolCall

        tctx = build_tool_context(db, admin, analysis_mode=False)
        tctx.skip_approval = True
        result = execute_tool(tctx, ToolCall(name=action_type, args=tool_args))
        resp = result.to_function_response()
        ok = result.success and not result.needs_approval
        output = {
            "action": action_type,
            "action_executed": ok,
            "response": resp,
            "task_answer": (
                resp.get("task_answer")
                or (f"FAIT — {action_type} exécuté après approbation." if ok else f"NON FAIT — {action_type}")
            ),
        }
        step.output_json = _safe_json_dumps(output)
        step.status = "completed" if ok else "failed"
        step.finished_at = _now()
        mission.status = "completed" if ok else "failed"
        mission.finished_at = _now()
        mission.updated_at = _now()
        _log(db, mission, f"Outil Globex exécuté — {action_type}", step_id=step.id)
        _record_mission_conversation(db, mission, mission.task_description, output)
        _notify_mission_lifecycle(db, mission, "complete", summary=str(output.get("task_answer") or ""))
    else:
        step.status = "running"
        step.started_at = step.started_at or _now()
        mission.status = "running"
        mission.updated_at = _now()
        db.flush()
        output = _execute_direct_mission(
            db, mission, step, actor_admin_id=admin.id, approved=True
        )
        _handle_step_output(db, mission, step, output)
        _record_mission_conversation(db, mission, mission.task_description, output)
        if step.status == "completed":
            mission.status = "completed"
            mission.finished_at = _now()
            _notify_mission_lifecycle(
                db, mission, "complete", summary=str(output.get("task_answer") or "")
            )
        db.commit()
        mission = db.scalar(
            select(AgentMission)
            .options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals))
            .where(AgentMission.id == approval.mission_id)
        )
        db.refresh(approval)
        return approval, _mission_read(mission)  # type: ignore[arg-type]

    db.commit()
    mission = db.scalar(
        select(AgentMission)
        .options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals))
        .where(AgentMission.id == approval.mission_id)
    )
    db.refresh(approval)
    return approval, _mission_read(mission)  # type: ignore[arg-type]


def reject_request(db: Session, approval_id: int, admin: User) -> tuple[AgentApprovalRequest, AgentMissionRead]:
    approval = db.scalar(select(AgentApprovalRequest).where(AgentApprovalRequest.id == approval_id))
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Demande déjà traitée")

    approval.status = "rejected"
    approval.resolved_by_admin_id = admin.id
    approval.resolved_at = _now()

    step = db.scalar(select(AgentMissionStep).where(AgentMissionStep.id == approval.step_id))
    if step:
        step.status = "skipped"
        step.finished_at = _now()

    mission = db.scalar(
        select(AgentMission).options(joinedload(AgentMission.steps), joinedload(AgentMission.approvals)).where(
            AgentMission.id == approval.mission_id
        )
    )
    if mission:
        mission.status = "failed"
        mission.finished_at = _now()
        _log(db, mission, f"Approbation refusée — {approval.description}", level="warning", step_id=approval.step_id)
    db.commit()
    db.refresh(approval)
    return approval, _mission_read(mission)  # type: ignore[arg-type]
