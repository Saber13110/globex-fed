"""Runtime unifié — exécution missions admin avec outils + cerveau Gemini."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.agent_mission import AgentMission
from app.models.agent_mission_step import AgentMissionStep
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.user import User, UserRole, UserStatus
from app.services.admin_agent_brain import (
    analyze_with_facts,
    draft_support_reply,
    plan_admin_mission,
    synthesize_mission_reply,
)
from app.services.admin_agent_tools import (
    ADMIN_TOOL_LABELS,
    SENSITIVE_TOOLS,
    admin_find_tracking_rows,
    aggregate_user_behavior,
    detect_forced_admin_tool,
    extract_email,
    extract_tracking_numbers,
    find_ticket_for_task,
    find_user_for_task,
    list_active_non_admin_users,
    list_suspended_non_admin_users,
    parse_tracking_intent,
    post_admin_support_reply,
    resolve_tool_for_mission,
    ticket_context_dict,
)
from app.services.admin_logs_export_service import (
    build_logs_export_download,
    fetch_activity_logs,
    generate_activity_logs_pdf,
    parse_log_period_hours,
)
from app.services.chat_export_service import generate_tracking_excel_bytes
from app.services.client_agent_brain import verify_agent_result
from app.services.email_service import is_email_configured, send_email_with_attachment
from app.services.security_ids_service import reactivate_user, suspend_user

logger = logging.getLogger(__name__)


def _step(label: str, status: str, detail: str | None = None) -> dict[str, Any]:
    return {"label": label, "status": status, "detail": detail}


def _reasoning_from_plan(plan: dict[str, Any] | None, tool: str, verified: bool | None, note: str) -> dict[str, Any]:
    if not plan:
        return {
            "objective": "",
            "plan": [],
            "action_tool": tool,
            "action_label": ADMIN_TOOL_LABELS.get(tool, tool),
            "verification": "",
            "verified": verified,
            "verification_note": note,
        }
    return {
        "objective": plan.get("objective") or "",
        "plan": plan.get("plan") or [],
        "action_tool": plan.get("action_tool") or tool,
        "action_label": ADMIN_TOOL_LABELS.get(tool, tool),
        "verification": plan.get("verification") or "",
        "verified": verified,
        "verification_note": note,
    }


def _execute_users_bulk_tool(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    tool: str,
    task: str,
    actor_admin_id: int,
    require_approval: bool,
    approved: bool,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    limit = mission.max_items
    if tool == "reactivate_all_suspended":
        users = list_suspended_non_admin_users(db, limit=limit)
        action_label = "réactivation"
        empty_msg = "INFORMATION — Aucun compte suspendu à réactiver."
    elif tool == "suspend_all_active":
        users = list_active_non_admin_users(db, limit=limit)
        action_label = "suspension"
        empty_msg = "INFORMATION — Aucun compte actif (hors admin) à suspendre."
    else:
        users = []

    output: dict[str, Any] = {
        "action": tool,
        "agent_type": "users",
        "task": task,
        "intent": tool,
        "action_executed": False,
        "analysis_only": False,
        "agent_steps": steps,
        "bulk_count": len(users),
    }
    step.action_type = tool
    step.is_sensitive = True

    steps.append(_step(f"Comptes ciblés ({len(users)})", "running"))
    if not users:
        steps.append(_step("Aucun compte", "warning"))
        output["task_answer"] = empty_msg
        return output

    preview = ", ".join(f"{u.email} (#{u.id})" for u in users[:5])
    if len(users) > 5:
        preview += f" … +{len(users) - 5} autre(s)"
    steps.append(_step("Liste établie", "done", preview))
    output["target_users"] = [
        {"user_id": u.id, "email": u.email, "full_name": u.full_name, "status": u.status}
        for u in users
    ]

    reason = f"Mission #{mission.id} — {task[:200]}"
    user_ids = [u.id for u in users]

    if require_approval and not approved:
        steps.append(_step("Approbation requise", "warning"))
        output.update(
            {
                "needs_approval": True,
                "approval_payload": {
                    "action_type": tool,
                    "user_ids": user_ids,
                    "emails": [u.email for u in users],
                    "count": len(users),
                    "reason": reason,
                },
                "task_answer": (
                    f"EN ATTENTE — {action_label} de {len(users)} compte(s).\n"
                    f"Cibles : {preview}\n"
                    "Approuvez pour exécuter."
                ),
            }
        )
        return output

    steps.append(_step("Exécution en lot", "running"))
    results: list[dict[str, Any]] = []
    ok_count = 0
    for u in users:
        status_before = u.status
        ok = False
        if tool == "reactivate_all_suspended":
            ok = reactivate_user(db, u.id, actor_admin_id=actor_admin_id)
            db.refresh(u)
            verified = ok and u.status == UserStatus.active.value
        else:
            ok = suspend_user(db, u.id, reason=reason, actor_admin_id=actor_admin_id)
            db.refresh(u)
            verified = ok and u.status == UserStatus.suspended.value
        if verified:
            ok_count += 1
        results.append(
            {
                "user_id": u.id,
                "email": u.email,
                "status_before": status_before,
                "status_after": u.status,
                "verified": verified,
            }
        )

    steps.append(_step("Vérification", "done" if ok_count == len(users) else "warning", f"{ok_count}/{len(users)}"))
    output["verification"] = {"results": results, "success_count": ok_count, "total": len(users)}
    output["action_executed"] = ok_count > 0
    verb = "réactivés" if tool == "reactivate_all_suspended" else "suspendus"
    if ok_count == len(users):
        output["task_answer"] = (
            f"FAIT — {ok_count} compte(s) {verb}.\n"
            + "\n".join(f"- {r['email']}: {r['status_before']} → {r['status_after']}" for r in results[:10])
            + (f"\n… et {len(results) - 10} autre(s)" if len(results) > 10 else "")
        )
    elif ok_count > 0:
        output["task_answer"] = (
            f"PARTIEL — {ok_count}/{len(users)} compte(s) {verb}.\n"
            "Consultez les logs pour le détail."
        )
    else:
        output["task_answer"] = f"NON FAIT — Échec {action_label} pour les {len(users)} compte(s)."
    return output


def _parse_user_target_hint(task: str) -> str:
    task_l = (task or "").lower()
    m = re.search(r"(?:user|utilisateur|compte)\s*#?\s*(\d+)|\bid\s*#?\s*(\d+)", task_l)
    if m:
        return f"ID {m.group(1) or m.group(2)}"
    email = extract_email(task or "")
    if email:
        return email
    return "cible à confirmer"


def _execute_users_tool(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    tool: str,
    task: str,
    actor_admin_id: int,
    require_approval: bool,
    approved: bool,
    steps: list[dict[str, Any]],
    catalog_task_id: str | None = None,
    mission_chain_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "action": tool,
        "agent_type": "users",
        "task": task,
        "intent": tool,
        "action_executed": False,
        "analysis_only": tool == "analyze_users",
        "agent_steps": steps,
    }
    if tool == "analyze_users":
        if catalog_task_id in _CATALOG_USERS_TASKS:
            from app.services.mission_catalog_runtime import execute_users_catalog_task
            from app.services.mission_task_catalog import get_task_spec

            catalog_out: dict[str, Any] | None = None
            try:
                catalog_out = execute_users_catalog_task(
                    db,
                    task,
                    catalog_task_id,
                    limit=mission.max_items or 30,
                    chain_context=mission_chain_context,
                )
            except Exception as exc:
                logger.exception("Users catalogue mission (%s)", catalog_task_id)
                spec = get_task_spec("users", catalog_task_id)
                catalog_out = _catalog_task_error(
                    "Users Agent",
                    spec.label if spec else catalog_task_id,
                    f"Erreur technique : {exc}",
                )
            if not catalog_out:
                spec = get_task_spec("users", catalog_task_id)
                catalog_out = _catalog_task_error(
                    "Users Agent",
                    spec.label if spec else catalog_task_id,
                    "Impossible d'exécuter la tâche catalogue utilisateurs.",
                )
            steps.append(_step("Utilisateurs catalogue", "done"))
            output.update(catalog_out)
            output["action"] = tool
            return output
        steps.append(_step("Analyse comptes", "running"))
        return output

    if tool in ("suspend_user", "reactivate_user") and require_approval and not approved:
        target_hint = _parse_user_target_hint(task)
        steps.append(_step("Approbation requise", "warning"))
        output.update(
            {
                "needs_approval": True,
                "approval_payload": {
                    "action_type": tool,
                    "target_hint": target_hint,
                    "reason": f"Mission #{mission.id} — {task[:200]}",
                },
                "task_answer": (
                    "Action sensible — approbation requise.\n"
                    f"Opération : {tool.replace('_', ' ')} pour {target_hint}.\n"
                    "Validez dans l'interface Agent Missions avant exécution."
                ),
            }
        )
        return output

    if tool in ("reactivate_all_suspended", "suspend_all_active"):
        return _execute_users_bulk_tool(
            db, mission, step, tool=tool, task=task,
            actor_admin_id=actor_admin_id, require_approval=require_approval,
            approved=approved, steps=steps,
        )

    user = find_user_for_task(db, task)
    if not user:
        steps.append(_step("Utilisateur introuvable", "error"))
        output["error"] = "user_not_found"
        output["task_answer"] = (
            "NON FAIT — Utilisateur introuvable.\nPrécisez email, #id ou nom exact."
        )
        return output

    output["target_user"] = {
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "status": user.status,
    }
    steps.append(_step(f"Cible : {user.email}", "done"))

    if user.role == UserRole.admin.value:
        output["task_answer"] = "NON FAIT — Impossible de modifier un compte administrateur."
        return output

    if tool == "suspend_user" and user.status == UserStatus.suspended.value:
        output["task_answer"] = f"INFORMATION — {user.email} est déjà suspendu."
        return output
    if tool == "reactivate_user" and user.status == UserStatus.active.value:
        output["task_answer"] = f"INFORMATION — {user.email} est déjà actif."
        return output

    step.action_type = tool
    step.is_sensitive = True
    reason = f"Mission #{mission.id} — {task[:200]}"

    if require_approval and not approved:
        steps.append(_step("Approbation requise", "warning"))
        output.update(
            {
                "needs_approval": True,
                "approval_payload": {
                    "action_type": tool,
                    "user_id": user.id,
                    "email": user.email,
                    "reason": reason,
                },
                "task_answer": (
                    f"EN ATTENTE — {tool.replace('_', ' ')} pour {user.email} (#{user.id}).\n"
                    "Approuvez pour exécuter."
                ),
            }
        )
        return output

    steps.append(_step("Exécution", "running"))
    status_before = user.status
    ok = False
    if tool == "suspend_user":
        ok = suspend_user(db, user.id, reason=reason, actor_admin_id=actor_admin_id)
    elif tool == "reactivate_user":
        ok = reactivate_user(db, user.id, actor_admin_id=actor_admin_id)
    db.refresh(user)
    verified = ok and (
        (tool == "suspend_user" and user.status == UserStatus.suspended.value)
        or (tool == "reactivate_user" and user.status == UserStatus.active.value)
    )
    output["verification"] = {
        "status_before": status_before,
        "status_after": user.status,
        "verified": verified,
    }
    output["action_executed"] = verified
    steps.append(_step("Vérification", "done" if verified else "error", user.status))
    label = "suspendu" if tool == "suspend_user" else "réactivé"
    output["task_answer"] = (
        f"FAIT — {user.email} {label}.\nVérification : {status_before} → {user.status}"
        if verified
        else f"NON FAIT — Échec {tool} pour {user.email}."
    )
    return output


def _execute_tracking_tool(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    tool: str,
    task: str,
    actor_admin_id: int,
    require_approval: bool,
    approved: bool,
    steps: list[dict[str, Any]],
    brain_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    params = (brain_plan or {}).get("parameters") or {}
    numbers = params.get("tracking_numbers") or extract_tracking_numbers(task)
    email_to = params.get("email_to") or extract_email(task)
    if isinstance(numbers, str):
        numbers = extract_tracking_numbers(numbers)

    output: dict[str, Any] = {
        "action": tool,
        "agent_type": "tracking",
        "task": task,
        "intent": tool,
        "tracking_numbers": numbers,
        "email_to": email_to,
        "action_executed": False,
        "analysis_only": tool == "analyze_tracking",
        "agent_steps": steps,
    }
    step.action_type = tool

    if tool in ("export_and_email_tracking", "export_tracking_excel"):
        steps.append(_step("Recherche colis en base", "running"))
        rows = admin_find_tracking_rows(db, numbers)
        found = [r.tracking_number for r in rows]
        missing = [n for n in numbers if n not in found]
        output["found_trackings"] = found
        output["missing_trackings"] = missing
        steps.append(_step(f"{len(found)} colis trouvés", "done" if found else "warning"))

        if not rows:
            output["task_answer"] = (
                "NON FAIT — Aucun colis trouvé en base pour : "
                + ", ".join(numbers or ["(aucun numéro détecté)"])
            )
            return output

        if tool == "export_and_email_tracking" and not email_to:
            output["task_answer"] = "NON FAIT — Adresse e-mail destinataire manquante."
            output["needs_clarification"] = True
            return output

        steps.append(_step("Génération Excel", "running"))
        excel_bytes = generate_tracking_excel_bytes(db, rows, include_events=True)
        output["excel_rows"] = len(rows)
        steps.append(_step("Excel généré", "done", f"{len(rows)} lignes"))

        if tool == "export_tracking_excel":
            output["action_executed"] = True
            output["analysis_only"] = False
            output["task_answer"] = (
                f"FAIT — Export Excel prêt ({len(rows)} colis).\n"
                f"Numéros : {', '.join(found)}"
                + (f"\nManquants en base : {', '.join(missing)}" if missing else "")
            )
            return output

        step.is_sensitive = True
        if require_approval and not approved:
            steps.append(_step("Approbation e-mail requise", "warning"))
            output.update(
                {
                    "needs_approval": True,
                    "approval_payload": {
                        "action_type": "send_email_with_attachment",
                        "email_to": email_to,
                        "tracking_numbers": found,
                        "mission_id": mission.id,
                        "excel_rows": len(rows),
                    },
                    "task_answer": (
                        f"EN ATTENTE — Envoi Excel ({len(rows)} colis) à {email_to}.\n"
                        "Approuvez pour envoyer."
                    ),
                }
            )
            return output

        if not is_email_configured():
            output["task_answer"] = (
                f"NON FAIT — SMTP non configuré. Excel généré pour {len(rows)} colis "
                f"({', '.join(found)}) mais e-mail non envoyé."
            )
            return output

        steps.append(_step(f"Envoi e-mail à {email_to}", "running"))
        sent = send_email_with_attachment(
            to=email_to,
            subject=f"[Globex FedEx] Export suivi — {len(rows)} colis",
            body_text=(
                f"Bonjour,\n\nVeuillez trouver ci-joint l'export Excel demandé "
                f"({len(rows)} colis).\n\n— Agent Globex FedEx"
            ),
            attachment_bytes=excel_bytes,
            attachment_filename="export-suivi-fedex.xlsx",
        )
        steps.append(_step("E-mail", "done" if sent else "error"))
        output["email_sent"] = sent
        output["action_executed"] = sent
        output["analysis_only"] = False
        output["verification"] = {"email_to": email_to, "verified": sent, "rows": len(rows)}
        output["task_answer"] = (
            f"FAIT — Excel ({len(rows)} colis) envoyé à {email_to}.\n"
            f"Colis : {', '.join(found)}"
            + (f"\nNon trouvés en base : {', '.join(missing)}" if missing else "")
            if sent
            else f"NON FAIT — Échec envoi e-mail à {email_to} (Excel généré)."
        )
        return output

    output["analysis_only"] = True
    return output


_CATALOG_SUPPORT_TASKS = frozenset({"ticket_list", "ticket_detail"})
_CATALOG_USERS_TASKS = frozenset({"user_list", "user_detail", "user_logs", "user_permissions"})


def _catalog_task_error(agent_label: str, task_label: str, detail: str) -> dict[str, Any]:
    msg = f"**NON FAIT — {task_label}** ({agent_label})\n\n{detail}"
    return {
        "task_answer": msg,
        "analysis": msg,
        "deterministic_compose": True,
        "analysis_only": True,
    }


def _execute_support_tool(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    tool: str,
    task: str,
    actor_admin_id: int,
    require_approval: bool,
    approved: bool,
    steps: list[dict[str, Any]],
    brain_plan: dict[str, Any] | None,
    catalog_task_id: str | None = None,
) -> dict[str, Any]:
    params = (brain_plan or {}).get("parameters") or {}
    ticket_id = params.get("ticket_id")
    ticket: SupportTicket | None = None
    if ticket_id:
        ticket = db.scalar(
            select(SupportTicket)
            .options(joinedload(SupportTicket.messages))
            .where(SupportTicket.id == int(ticket_id))
        )
    if not ticket:
        ticket = find_ticket_for_task(db, task)
        if ticket:
            ticket = db.scalar(
                select(SupportTicket)
                .options(joinedload(SupportTicket.messages))
                .where(SupportTicket.id == ticket.id)
            )

    output: dict[str, Any] = {
        "action": tool,
        "agent_type": "support",
        "task": task,
        "intent": tool,
        "action_executed": False,
        "analysis_only": tool == "analyze_tickets",
        "agent_steps": steps,
    }
    step.action_type = tool

    if catalog_task_id in _CATALOG_SUPPORT_TASKS and tool == "analyze_tickets":
        from app.services.mission_catalog_runtime import execute_support_catalog_task
        from app.services.mission_task_catalog import get_task_spec

        catalog_out: dict[str, Any] | None = None
        try:
            catalog_out = execute_support_catalog_task(
                db,
                task,
                catalog_task_id,
                limit=mission.max_items or 30,
            )
        except Exception as exc:
            logger.exception("Support catalogue mission (%s)", catalog_task_id)
            spec = get_task_spec("support", catalog_task_id)
            catalog_out = _catalog_task_error(
                "Support Agent",
                spec.label if spec else catalog_task_id,
                f"Erreur technique : {exc}",
            )
        if not catalog_out:
            spec = get_task_spec("support", catalog_task_id)
            catalog_out = _catalog_task_error(
                "Support Agent",
                spec.label if spec else catalog_task_id,
                "Impossible d'exécuter la tâche catalogue support.",
            )
        steps.append(_step("Tickets catalogue", "done" if catalog_out.get("deterministic_compose") else "error"))
        output.update(catalog_out)
        output["action"] = tool
        return output

    if tool == "analyze_tickets":
        from app.services.gpt.tool_handlers import HANDLERS
        from app.services.gpt.tool_types import ToolExecutionContext

        task_l = (task or "").lower()
        if re.search(r"\b(fermé|fermes|closed)\b", task_l):
            status_filter = "closed"
        elif re.search(r"\b(résolu|resolu|resolved)\b", task_l):
            status_filter = "resolved"
        elif re.search(r"\b(pending|en attente)\b", task_l):
            status_filter = "pending"
        else:
            status_filter = "open"

        tool_ctx = ToolExecutionContext(
            db=db,
            user_id=actor_admin_id,
            user_role="admin",
            gpt_slug="fedex-admin-ops",
            actor_admin_id=actor_admin_id,
            ui_language="fr",
        )
        handler = HANDLERS.get("analyze_tickets")
        result = handler(tool_ctx, {"status": status_filter, "limit": 30}) if handler else None
        tickets = (result.data.get("tickets") or []) if result and result.success else []
        count = (result.data.get("count") or len(tickets)) if result and result.success else 0

        steps.append(_step("Analyse tickets", "done", f"{count} ticket(s)"))
        output["tickets_sample"] = tickets
        output["tickets_count"] = count
        if not tickets:
            output["task_answer"] = (
                f"Aucun ticket avec le statut « {status_filter} » pour le moment."
            )
        else:
            lines = [
                f"- #{t['id']} [{t.get('status', '?')}] {(t.get('subject') or '')[:100]}"
                for t in tickets
            ]
            output["task_answer"] = (
                f"Tickets ({status_filter}) — {count} trouvé(s) :\n" + "\n".join(lines)
            )
        return output

    steps.append(_step("Recherche ticket", "running"))
    if not ticket:
        steps.append(_step("Ticket introuvable", "error"))
        output["error"] = "ticket_not_found"
        output["task_answer"] = (
            "NON FAIT — Ticket introuvable.\n"
            "Précisez l'ID (#12), le numéro TKT-… ou le sujet entre guillemets."
        )
        return output

    output["target_ticket"] = {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "status": ticket.status,
    }
    steps.append(_step(f"Ticket #{ticket.id}", "done", ticket.subject[:60]))

    if ticket.status == SupportTicketStatus.closed:
        output["task_answer"] = f"NON FAIT — Le ticket #{ticket.id} est fermé."
        return output

    steps.append(_step("Rédaction réponse", "running"))
    ticket_ctx = ticket_context_dict(ticket)
    reply_hint = str(params.get("reply_hint") or params.get("reply_body") or "")
    draft = draft_support_reply(task, ticket_ctx, reply_hint=reply_hint)
    output["draft_reply"] = draft
    steps.append(_step("Brouillon prêt", "done"))

    step.is_sensitive = True
    if require_approval and not approved:
        steps.append(_step("Approbation requise", "warning"))
        output.update(
            {
                "needs_approval": True,
                "approval_payload": {
                    "action_type": "reply_support_ticket",
                    "ticket_id": ticket.id,
                    "subject": ticket.subject,
                    "reply_body": draft,
                    "mission_id": mission.id,
                },
                "task_answer": (
                    f"EN ATTENTE — Réponse au ticket #{ticket.id} « {ticket.subject} ».\n\n"
                    f"Brouillon :\n{draft[:500]}{'…' if len(draft) > 500 else ''}\n\n"
                    "Approuvez pour publier la réponse au client."
                ),
            }
        )
        return output

    steps.append(_step("Publication réponse", "running"))
    ok, verification = post_admin_support_reply(
        db, ticket_id=ticket.id, body=draft, admin_id=actor_admin_id
    )
    steps.append(_step("Vérification", "done" if ok else "error"))
    output["verification"] = verification
    output["action_executed"] = ok
    output["analysis_only"] = False
    output["task_answer"] = (
        f"FAIT — Réponse publiée sur le ticket #{ticket.id} « {ticket.subject} ».\n"
        f"Statut : {verification.get('status_after', ticket.status)}"
        if ok
        else f"NON FAIT — Échec publication ticket #{ticket.id} ({verification.get('error', 'erreur')})."
    )
    return output


def _run_analyst(task: str, facts: dict[str, Any], output: dict[str, Any]) -> str:
    answer, degraded = analyze_with_facts(task, facts)
    if degraded:
        output["llm_degraded"] = True
    return answer


def _mark_running_step_done(steps: list[dict[str, Any]]) -> None:
    if steps and steps[-1].get("status") == "running":
        steps[-1]["status"] = "done"


def _admin_clarification_output(
    brain_plan: dict[str, Any],
    tool: str,
    task: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Question unique Gemini — même logique que le client."""
    flow_id = str(uuid.uuid4())
    question = str(brain_plan.get("clarification_question") or "Pouvez-vous préciser votre demande ?").strip()
    intro = str(brain_plan.get("assistant_intro") or brain_plan.get("objective") or "").strip()
    steps.append(_step("Clarification requise", "warning"))
    steps.append(_step("Terminé", "warning", "En attente de réponse"))
    reply = f"{intro}\n\n{question}".strip() if intro else question
    return {
        "action": tool,
        "task": task,
        "intent": tool,
        "action_executed": False,
        "analysis_only": True,
        "needs_clarification": True,
        "agent_steps": steps,
        "task_answer": reply,
        "analysis": reply,
        "agent_questionnaire": {
            "flow_id": flow_id,
            "task_type": tool,
            "task_label": ADMIN_TOOL_LABELS.get(tool, tool),
            "intro": intro or reply,
            "questions": [
                {
                    "id": "clarification",
                    "label": question,
                    "question_type": "text",
                    "options": [],
                    "required": True,
                }
            ],
            "allow_multiple_submit": True,
        },
        "agent_reasoning": _reasoning_from_plan(brain_plan, tool, None, "Clarification requise avant exécution"),
    }


def _execute_logs_tool(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    tool: str,
    task: str,
    steps: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hours = parse_log_period_hours(task, default=24)
    output: dict[str, Any] = {
        "action": tool,
        "agent_type": mission.agent_type,
        "task": task,
        "intent": tool,
        "action_executed": False,
        "analysis_only": True,
        "agent_steps": steps,
        "period_hours": hours,
    }
    step.action_type = tool
    _mark_running_step_done(steps)

    if tool == "export_activity_logs_pdf":
        steps.append(_step(f"Lecture logs ({hours}h)", "running"))
        try:
            logs = fetch_activity_logs(db, hours=hours, limit=mission.max_items or 500)
            steps.append(_step("Génération PDF", "running"))
            pdf_bytes, filename = generate_activity_logs_pdf(logs, hours=hours)
            steps.append(_step("PDF prêt", "done", f"{len(logs)} entrées"))
            output.update(
                {
                    "action_executed": True,
                    "analysis_only": False,
                    "logs_count": len(logs),
                    "export_download": build_logs_export_download(hours, fmt="pdf"),
                    "pdf_bytes_hint": len(pdf_bytes),
                    "task_answer": (
                        f"FAIT — J'ai généré le PDF : **{len(logs)} entrées** sur les **{hours} dernières heures**.\n"
                        f"Cliquez sur le lien ci-dessous pour télécharger `{filename}`."
                    ),
                }
            )
        except Exception as exc:
            steps.append(_step("Échec export PDF", "error", str(exc)[:120]))
            output["task_answer"] = (
                f"NON FAIT — Impossible de générer le PDF des logs ({hours}h).\n"
                f"Détail : {exc}"
            )
        return output

    if tool == "export_activity_logs_excel":
        from app.services.admin_logs_export_service import generate_activity_logs_excel

        steps.append(_step(f"Lecture logs ({hours}h)", "running"))
        try:
            logs = fetch_activity_logs(db, hours=hours, limit=mission.max_items or 500)
            steps.append(_step("Génération Excel", "running"))
            excel_bytes, filename = generate_activity_logs_excel(logs, hours=hours)
            steps.append(_step("Excel prêt", "done", f"{len(logs)} entrées"))
            output.update(
                {
                    "action_executed": True,
                    "analysis_only": False,
                    "logs_count": len(logs),
                    "export_download": build_logs_export_download(hours, fmt="xlsx"),
                    "excel_bytes_hint": len(excel_bytes),
                    "task_answer": (
                        f"FAIT — J'ai généré l'Excel : **{len(logs)} entrées** sur les **{hours} dernières heures** "
                        f"(colonnes Date, Titre, Type de log).\n"
                        f"Cliquez sur le lien ci-dessous pour télécharger `{filename}`."
                    ),
                }
            )
        except Exception as exc:
            steps.append(_step("Échec export Excel", "error", str(exc)[:120]))
            output["task_answer"] = (
                f"NON FAIT — Impossible de générer l'Excel des logs ({hours}h).\n"
                f"Détail : {exc}"
            )
        return output

    if tool == "daily_behavior_report":
        steps.append(_step(f"Agrégation logs ({hours}h)", "running"))
        behavior = aggregate_user_behavior(db, hours=hours, limit_users=mission.max_items)
        steps.append(_step("Analyse comportements", "running"))
        answer = _run_analyst(task, {**(context or {}), "behavior": behavior}, output)
        steps.append(_step("Synthèse analyste", "done"))
        output.update(
            {
                "behavior_snapshot": behavior,
                "task_answer": answer,
                "analysis": answer,
            }
        )
        return output

    if tool == "analyze_logs":
        steps.append(_step(f"Lecture logs ({hours}h)", "running"))
        logs = fetch_activity_logs(db, hours=hours, limit=min(mission.max_items or 50, 100))
        sample = [
            {
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "level": row.level,
                "action": row.action,
                "message": (row.message or "")[:200],
                "category": row.category,
            }
            for row in logs
        ]
        steps.append(_step("Analyse IA", "running"))
        answer = _run_analyst(task, {**(context or {}), "logs_sample": sample, "logs_count": len(logs), "period_hours": hours}, output)
        steps.append(_step("Synthèse", "done"))
        output.update({"task_answer": answer, "analysis": answer, "logs_sample": sample})
        return output

    steps.append(_step("Synthèse globale", "running"))
    answer = _run_analyst(task, context or {}, output)
    steps.append(_step("Synthèse", "done"))
    output.update({"task_answer": answer, "analysis": answer})
    return output


_LOG_MISSION_TOOLS = frozenset(
    {
        "analyze_logs",
        "export_activity_logs_pdf",
        "export_activity_logs_excel",
        "daily_behavior_report",
        "generate_summary",
    }
)
_SECURITY_MISSION_TOOLS = frozenset({"analyze_security", "analyze_notifications"})


def _execute_security_tool(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    tool: str,
    task: str,
    steps: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
    catalog_task_id: str | None = None,
) -> dict[str, Any]:
    from app.services.admin_client.security import security_tool
    from app.services.admin_client.security.security_compose import compose_security_response
    from app.services.admin_client.security.security_types import (
        SecurityPlan,
        SecurityProfile,
        SecurityTaskType,
    )
    from app.services.mission_task_runner import (
        security_plan_for_catalog_task,
        task_wants_security_incident_list,
    )

    output: dict[str, Any] = {
        "action": tool,
        "agent_type": mission.agent_type,
        "task": task,
        "intent": tool,
        "action_executed": False,
        "analysis_only": True,
        "agent_steps": steps,
    }
    step.action_type = tool
    _mark_running_step_done(steps)

    limit = min(int(mission.max_items or 15), 50)
    plan = security_plan_for_catalog_task(catalog_task_id, limit=limit)

    if plan is None and tool == "analyze_security" and task_wants_security_incident_list(task, catalog_task_id):
        plan = SecurityPlan(
            task_type=SecurityTaskType.security_incident_list,
            profile=SecurityProfile.LIST,
            status_filter="open",
            limit=limit,
        )

    if plan is not None:
        try:
            if plan.profile == SecurityProfile.LIST:
                steps.append(_step("Chargement incidents sécurité", "running"))
                processed = security_tool.list_incidents(db, plan)
                processed["filters"] = plan
                answer = compose_security_response(processed, plan, lang="fr")
                count = len(processed.get("incidents") or [])
                steps.append(_step("Liste incidents IDS", "done", f"{count} ligne(s)"))
                incident_ids = [
                    int(i["id"])
                    for i in (processed.get("incidents") or [])
                    if isinstance(i, dict) and i.get("id") is not None
                ]
                output.update(
                    {
                        "security_incidents_count": count,
                        "security_incidents_open": processed.get("open_count", 0),
                        "security_incidents": processed.get("incidents") or [],
                        "task_answer": answer,
                        "analysis": answer,
                        "deterministic_compose": True,
                        "chain_context": {"security_incident_ids": incident_ids},
                        "agent_reasoning": (
                            "Objectif : lister les incidents de sécurité récents.\n\n"
                            "Action : list_incidents (IDS) → tableau structuré.\n\n"
                            "Vérification : chaque incident affiche id, date, sévérité, menace et titre."
                        ),
                    }
                )
                return output

            if plan.profile == SecurityProfile.SUMMARY:
                steps.append(_step("Synthèse incidents", "running"))
                summary = security_tool.build_summary(db, plan)
                answer = compose_security_response({"summary": summary}, plan, lang="fr")
                steps.append(_step("Synthèse", "done"))
                output.update(
                    {
                        "task_answer": answer,
                        "analysis": answer,
                        "deterministic_compose": True,
                    }
                )
                return output

            if plan.profile == SecurityProfile.SCAN:
                steps.append(_step("Scan IDS", "running"))
                scan = security_tool.run_scan(db, plan)
                answer = compose_security_response({"scan": scan}, plan, lang="fr")
                steps.append(_step("Scan terminé", "done"))
                output.update(
                    {
                        "task_answer": answer,
                        "analysis": answer,
                        "deterministic_compose": True,
                    }
                )
                return output

            if plan.profile == SecurityProfile.REPORT:
                steps.append(_step("Rapport sécurité", "running"))
                report = security_tool.build_report(db)
                answer = compose_security_response({"report": report}, plan, lang="fr")
                steps.append(_step("Rapport prêt", "done"))
                output.update(
                    {
                        "task_answer": answer,
                        "analysis": answer,
                        "deterministic_compose": True,
                    }
                )
                return output

            if plan.profile == SecurityProfile.DETAIL:
                from app.services.admin_client.security.security_followup import (
                    extract_incident_ref,
                    format_incident_ids_hint,
                    resolve_incident_id_from_context,
                )
                from app.services.mission_task_runner import split_prior_context

                user_part, prior_context = split_prior_context(task)
                history = prior_context or task
                ref = extract_incident_ref(user_part or task, history_text=history)
                incident_id = (
                    resolve_incident_id_from_context(db, ref, history_text=history)
                    if ref is not None
                    else None
                )
                if incident_id:
                    steps.append(_step(f"Incident #{incident_id}", "running"))
                    incident = security_tool.get_incident_detail(db, int(incident_id))
                    answer = compose_security_response({"incident": incident}, plan, lang="fr")
                    steps.append(_step("Fiche incident", "done"))
                    output.update(
                        {
                            "task_answer": answer,
                            "analysis": answer,
                            "deterministic_compose": True,
                            "security_incident_id": incident_id,
                            "chain_context": {"security_incident_id": incident_id},
                        }
                    )
                    return output

                hint = format_incident_ids_hint(history, lang="fr")
                clarify = (
                    "Je n'ai pas pu identifier l'incident à analyser.\n\n"
                    "Indiquez **incident #ID** (ID en base) ou **#N** pour la Nᵉ ligne du tableau "
                    "de l'étape précédente (ex. `#2` = 2ᵉ ligne)."
                    f"{hint}"
                )
                steps.append(_step("Incident introuvable", "error"))
                output.update(
                    {
                        "task_answer": clarify,
                        "analysis": clarify,
                        "needs_clarification": True,
                        "deterministic_compose": True,
                    }
                )
                return output
        except Exception as exc:  # noqa: BLE001
            steps.append(_step("Erreur sécurité IDS", "error", str(exc)[:120]))
            output["task_answer"] = f"NON FAIT — Impossible de récupérer les incidents IDS.\nDétail : {exc}"
            output["analysis"] = output["task_answer"]
            return output

    if tool == "analyze_security":
        from app.services.security_ids_service import incident_to_read, list_incidents

        steps.append(_step("Chargement incidents sécurité", "running"))
        rows, total, open_count = list_incidents(db, status="open", limit=limit)
        sample = [incident_to_read(db, row) for row in rows]
        steps.append(_step("Incidents IDS", "done", f"{len(sample)} / {open_count} ouvert(s)"))
        security_ctx = {
            "task": task,
            "agent_type": mission.agent_type,
            "security_incidents": sample,
            "security_incidents_total": total,
            "security_incidents_open": open_count,
            "focus": "incidents_ids_only",
            "instruction": (
                "Réponds UNIQUEMENT sur les incidents IDS listés dans security_incidents. "
                "Ne mentionne pas les suspensions admin, les logs généraux ni les utilisateurs "
                "sauf s'ils sont liés à un incident du tableau."
            ),
        }
        steps.append(_step("Analyse sécurité", "running"))
        answer = _run_analyst(task, security_ctx, output)
        steps.append(_step("Synthèse", "done"))
        output.update(
            {
                "security_incidents_count": len(sample),
                "security_incidents_open": open_count,
                "task_answer": answer,
                "analysis": answer,
            }
        )
        return output

    steps.append(_step("Notifications plateforme", "running"))
    notif_ctx = {
        "task": task,
        "agent_type": mission.agent_type,
        "notifications_unread": (context or {}).get("notifications_unread"),
    }
    answer = _run_analyst(task, notif_ctx, output)
    steps.append(_step("Synthèse", "done"))
    output.update({"task_answer": answer, "analysis": answer})
    return output


def execute_admin_mission_task(
    db: Session,
    mission: AgentMission,
    step: AgentMissionStep,
    *,
    task: str,
    actor_admin_id: int,
    require_approval: bool = True,
    approved: bool = False,
    context: dict[str, Any] | None = None,
    catalog_tool_hint: str | None = None,
    source_agent_type: str | None = None,
    catalog_task_id: str | None = None,
    mission_chain_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Point d'entrée unique : plan → outils → synthèse."""
    steps: list[dict[str, Any]] = []
    objective_hint = (task or "")[:80]
    steps.append(_step("Objectif", "running", objective_hint))

    forced_tool = detect_forced_admin_tool(task)
    resolved_tool = resolve_tool_for_mission(mission, task)
    tool = catalog_tool_hint or forced_tool or resolved_tool

    brain_agent = source_agent_type or mission.agent_type
    ctx_summary = json.dumps(context or {}, ensure_ascii=False, default=str)[:4000]
    brain_plan = plan_admin_mission(task, agent_type=brain_agent, context_summary=ctx_summary)

    if brain_plan and brain_plan.get("objective"):
        steps[0] = _step("Objectif", "done", str(brain_plan["objective"])[:100])
    else:
        steps[0] = _step("Objectif", "done", objective_hint)

    if (
        not forced_tool
        and brain_plan
        and brain_plan.get("needs_clarification")
        and brain_plan.get("clarification_question")
        and not brain_plan.get("ready_to_execute", False)
    ):
        return _admin_clarification_output(brain_plan, tool, task, steps)

    if catalog_tool_hint:
        tool = catalog_tool_hint
    elif brain_plan and brain_plan.get("action_tool") and not forced_tool:
        brain_tool = str(brain_plan["action_tool"])
        bulk_tools = {"reactivate_all_suspended", "suspend_all_active"}
        export_tools = {
            "export_activity_logs_pdf",
            "export_activity_logs_excel",
            "export_tracking_excel",
            "export_and_email_tracking",
        }
        is_security_agent = mission.agent_type in ("security", "notifications") or (
            source_agent_type in ("security", "notifications")
        )
        if is_security_agent:
            tool = resolved_tool
            if brain_tool in _SECURITY_MISSION_TOOLS:
                tool = brain_tool
            elif brain_tool not in _LOG_MISSION_TOOLS:
                tool = resolved_tool
        elif resolved_tool in bulk_tools or resolved_tool in export_tools:
            tool = resolved_tool
        elif brain_tool in export_tools and detect_forced_admin_tool(task):
            tool = detect_forced_admin_tool(task) or resolved_tool
        else:
            tool = brain_tool
    elif forced_tool:
        tool = forced_tool

    steps.append(_step("Plan agent", "done", tool))
    steps.append(_step(ADMIN_TOOL_LABELS.get(tool, tool), "running"))

    output: dict[str, Any]

    if mission.agent_type == "users":
        output = _execute_users_tool(
            db, mission, step, tool=tool, task=task,
            actor_admin_id=actor_admin_id, require_approval=require_approval,
            approved=approved, steps=steps,
            catalog_task_id=catalog_task_id,
            mission_chain_context=mission_chain_context,
        )
        if output.get("analysis_only") and not output.get("task_answer") and context:
            if output.get("deterministic_compose"):
                pass
            else:
                answer = _run_analyst(task, context, output)
                output["task_answer"] = answer
                output["analysis"] = answer
                steps.append(_step("Analyse IA", "done"))
    elif mission.agent_type == "tracking":
        output = _execute_tracking_tool(
            db, mission, step, tool=tool, task=task,
            actor_admin_id=actor_admin_id, require_approval=require_approval,
            approved=approved, steps=steps, brain_plan=brain_plan,
        )
        if output.get("analysis_only") and not output.get("task_answer") and context:
            answer = _run_analyst(task, context, output)
            output["task_answer"] = answer
            output["analysis"] = answer
            steps.append(_step("Analyse IA", "done"))
    elif mission.agent_type == "support":
        output = _execute_support_tool(
            db, mission, step, tool=tool, task=task,
            actor_admin_id=actor_admin_id, require_approval=require_approval,
            approved=approved, steps=steps, brain_plan=brain_plan,
            catalog_task_id=catalog_task_id,
        )
        if output.get("analysis_only") and not output.get("task_answer") and context:
            if output.get("deterministic_compose"):
                pass
            else:
                answer = _run_analyst(task, context, output)
                output["task_answer"] = answer
                output["analysis"] = answer
                steps.append(_step("Analyse IA", "done"))
    elif mission.agent_type in ("security", "notifications") or (
        source_agent_type in ("security", "notifications")
    ):
        output = _execute_security_tool(
            db,
            mission,
            step,
            tool=tool,
            task=task,
            steps=steps,
            context=context,
            catalog_task_id=catalog_task_id,
        )
    elif mission.agent_type in ("logs", "summary", "reports") or tool in (
        "daily_behavior_report",
        "export_activity_logs_pdf",
        "export_activity_logs_excel",
        "analyze_logs",
        "generate_summary",
    ):
        output = _execute_logs_tool(
            db,
            mission,
            step,
            tool=tool,
            task=task,
            steps=steps,
            context=context,
        )
    else:
        output = {
            "action": tool,
            "agent_type": mission.agent_type,
            "task": task,
            "action_executed": False,
            "analysis_only": True,
            "agent_steps": steps,
        }
        step.action_type = tool
        if context:
            answer = _run_analyst(task, context, output)
            output["task_answer"] = answer
            output["analysis"] = answer
            steps.append(_step("Analyse IA", "done"))

    if not output.get("task_answer"):
        output["analysis_only"] = True

    verified = output.get("action_executed") if "action_executed" in output else None
    note = (output.get("verification") or {}) if isinstance(output.get("verification"), dict) else {}
    verified_note = str(note)[:300] if note else ""

    technical = output.get("task_answer") or ""
    steps_summary = "\n".join(f"- {s['label']}: {s.get('detail') or s['status']}" for s in steps)

    if (
        brain_plan
        and technical
        and not output.get("needs_clarification")
        and not output.get("llm_degraded")
    ):
        vresult = verify_agent_result(
            objective=str(brain_plan.get("objective") or ""),
            verification=str(brain_plan.get("verification") or ""),
            task=tool,
            technical_result=technical,
            steps_summary=steps_summary,
        )
        if vresult.get("verified") is not None:
            verified = vresult["verified"]
        if vresult.get("note"):
            verified_note = str(vresult["note"])[:300]

    output["agent_reasoning"] = (
        output.get("agent_reasoning")
        if output.get("deterministic_compose")
        else _reasoning_from_plan(
            brain_plan,
            tool,
            verified if isinstance(verified, bool) else None,
            verified_note,
        )
    )
    output["agent_steps"] = steps

    if output.get("export_download"):
        pass
    elif output.get("needs_clarification"):
        pass
    elif not output.get("analysis_only") or output.get("action_executed"):
        natural = synthesize_mission_reply(
            task=task,
            tool=tool,
            technical_result=technical,
            steps_summary=steps_summary,
        )
        if natural:
            output["task_answer"] = natural
            output["analysis"] = natural

    _mark_running_step_done(steps)
    steps.append(_step("Terminé", "done" if output.get("action_executed") or output.get("export_download") else (
        "warning" if output.get("needs_clarification") else "done" if output.get("analysis_only") else "warning"
    )))
    output["agent_steps"] = steps
    return output


def execute_approved_email_attachment(
    db: Session,
    *,
    email_to: str,
    tracking_numbers: list[str],
    mission_id: int,
) -> dict[str, Any]:
    """Exécute l'envoi e-mail Excel après approbation admin."""
    steps: list[dict[str, Any]] = [_step("Approbation reçue", "done")]
    rows = admin_find_tracking_rows(db, tracking_numbers)
    found = [r.tracking_number for r in rows]
    if not rows:
        return {
            "action_executed": False,
            "task_answer": f"NON FAIT — Aucun colis trouvé pour : {', '.join(tracking_numbers)}",
            "agent_steps": steps,
        }
    steps.append(_step("Génération Excel", "running"))
    excel_bytes = generate_tracking_excel_bytes(db, rows, include_events=True)
    steps.append(_step("Excel généré", "done", f"{len(rows)} lignes"))
    if not is_email_configured():
        return {
            "action_executed": False,
            "task_answer": "NON FAIT — SMTP non configuré.",
            "agent_steps": steps,
        }
    steps.append(_step(f"Envoi e-mail à {email_to}", "running"))
    sent = send_email_with_attachment(
        to=email_to,
        subject=f"[Globex FedEx] Export suivi — {len(rows)} colis",
        body_text=(
            f"Bonjour,\n\nVeuillez trouver ci-joint l'export Excel demandé "
            f"({len(rows)} colis).\n\n— Agent Globex FedEx (mission #{mission_id})"
        ),
        attachment_bytes=excel_bytes,
        attachment_filename="export-suivi-fedex.xlsx",
    )
    steps.append(_step("E-mail", "done" if sent else "error"))
    return {
        "action": "send_email_with_attachment",
        "action_executed": sent,
        "email_sent": sent,
        "email_to": email_to,
        "found_trackings": found,
        "verification": {"email_to": email_to, "verified": sent, "rows": len(rows)},
        "task_answer": (
            f"FAIT — Excel ({len(rows)} colis) envoyé à {email_to} après approbation.\n"
            f"Colis : {', '.join(found)}"
            if sent
            else f"NON FAIT — Échec envoi e-mail à {email_to}."
        ),
        "agent_steps": steps,
    }


def execute_approved_support_reply(
    db: Session,
    *,
    ticket_id: int,
    reply_body: str,
    admin_id: int,
    mission_id: int,
) -> dict[str, Any]:
    """Publie une réponse support après approbation admin."""
    steps: list[dict[str, Any]] = [_step("Approbation reçue", "done")]
    steps.append(_step(f"Ticket #{ticket_id}", "running"))
    ok, verification = post_admin_support_reply(
        db, ticket_id=ticket_id, body=reply_body, admin_id=admin_id
    )
    steps.append(_step("Publication", "done" if ok else "error"))
    subject = verification.get("subject") or ""
    return {
        "action": "reply_support_ticket",
        "action_executed": ok,
        "verification": verification,
        "task_answer": (
            f"FAIT — Réponse publiée sur le ticket #{ticket_id}"
            + (f" « {subject} »" if subject else "")
            + " après approbation."
            if ok
            else f"NON FAIT — Échec publication ticket #{ticket_id} ({verification.get('error', 'erreur')})."
        ),
        "agent_steps": steps,
        "mission_id": mission_id,
    }


def execute_approved_bulk_users(
    db: Session,
    *,
    action_type: str,
    user_ids: list[int],
    admin_id: int,
    mission_id: int,
    reason: str = "",
) -> dict[str, Any]:
    """Exécute une action utilisateurs en lot après approbation."""
    steps: list[dict[str, Any]] = [_step("Approbation reçue", "done")]
    users = list(db.scalars(select(User).where(User.id.in_(user_ids))).all())
    if not users:
        return {
            "action_executed": False,
            "task_answer": "NON FAIT — Aucun compte trouvé pour l'approbation.",
            "agent_steps": steps,
        }
    steps.append(_step(f"Exécution ({len(users)} comptes)", "running"))
    results: list[dict[str, Any]] = []
    ok_count = 0
    for u in users:
        if u.role == UserRole.admin.value:
            results.append({"user_id": u.id, "email": u.email, "verified": False, "skip": "admin"})
            continue
        status_before = u.status
        ok = False
        if action_type == "reactivate_all_suspended":
            ok = reactivate_user(db, u.id, actor_admin_id=admin_id)
        elif action_type == "suspend_all_active":
            ok = suspend_user(db, u.id, reason=reason or f"Mission #{mission_id}", actor_admin_id=admin_id)
        db.refresh(u)
        verified = ok and (
            (action_type == "reactivate_all_suspended" and u.status == UserStatus.active.value)
            or (action_type == "suspend_all_active" and u.status == UserStatus.suspended.value)
        )
        if verified:
            ok_count += 1
        results.append(
            {
                "user_id": u.id,
                "email": u.email,
                "status_before": status_before,
                "status_after": u.status,
                "verified": verified,
            }
        )
    verb = "réactivés" if action_type == "reactivate_all_suspended" else "suspendus"
    steps.append(_step("Vérification", "done" if ok_count == len(users) else "warning", f"{ok_count}/{len(users)}"))
    return {
        "action": action_type,
        "action_executed": ok_count > 0,
        "verification": {"results": results, "success_count": ok_count, "total": len(users)},
        "task_answer": (
            f"FAIT — {ok_count} compte(s) {verb} après approbation.\n"
            + "\n".join(f"- {r['email']}: {r['status_before']} → {r['status_after']}" for r in results[:10] if r.get("verified"))
            + (f"\n… et {ok_count - 10} autre(s)" if ok_count > 10 else "")
            if ok_count > 0
            else f"NON FAIT — Échec action en lot ({action_type})."
        ),
        "agent_steps": steps,
        "mission_id": mission_id,
    }
