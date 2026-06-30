"""Réponses déterministes Mission Control admin."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.missions.missions_pending import (
    MISSIONS_CONFIRM_MARKER_FR,
    build_missions_pending_marker,
)
from app.services.admin_client.missions.missions_types import MissionsPlan, MissionsProfile, MissionsTaskType
from app.services.agent_mission_service import AGENT_LABELS


def compose_missions_response(
    processed: dict[str, Any],
    plan: MissionsPlan,
    *,
    lang: str = "fr",
    error_code: str | None = None,
    action_result: dict[str, Any] | None = None,
) -> str:
    if error_code:
        return _error_text(error_code, lang)
    if plan.profile == MissionsProfile.LIST:
        return _compose_list(processed, lang)
    if plan.profile == MissionsProfile.RESULTS:
        return _compose_results(processed, lang)
    if plan.profile == MissionsProfile.LOGS:
        return _compose_logs_summary(processed, lang)
    if plan.profile == MissionsProfile.CONFIRM:
        return _compose_confirm(processed, plan, lang)
    if plan.profile == MissionsProfile.CONFIRM_DELETE:
        return _compose_confirm_delete(processed, plan, lang)
    if plan.profile == MissionsProfile.DONE:
        return _compose_done(processed, plan, action_result or {}, lang)
    if plan.profile == MissionsProfile.CLARIFY:
        return plan.clarification_question or default_clarify(lang)
    if plan.profile == MissionsProfile.ERROR:
        return f"**{'Erreur' if lang == 'fr' else 'Error'}** — {processed.get('message', '—')}"
    return _compose_list(processed, lang)


def default_clarify(lang: str) -> str:
    if lang == "en":
        return "Could you clarify your agent mission request?"
    return "Pouvez-vous préciser votre demande concernant les missions agent ?"


def _error_text(code: str, lang: str) -> str:
    catalog_fr = {
        "mission_not_found": "Mission introuvable.",
        "fetch_failed": "Impossible de récupérer les missions en temps réel.",
        "invalid_state": "Action impossible pour le statut actuel de la mission.",
        "pending_parse_failed": "Confirmation expirée — recommencez l'action.",
    }
    catalog_en = {
        "mission_not_found": "Mission not found.",
        "fetch_failed": "Could not fetch live mission data.",
        "invalid_state": "Action not allowed for the current mission status.",
        "pending_parse_failed": "Confirmation expired — please start again.",
    }
    catalog = catalog_en if lang == "en" else catalog_fr
    label = "Erreur" if lang == "fr" else "Error"
    return f"**{label}** — {catalog.get(code, code)}"


def _mission_link(mission_id: int) -> str:
    return f"/admin/agent-missions/{mission_id}"


def _compose_list(processed: dict[str, Any], lang: str) -> str:
    items = processed.get("items") or []
    stats = processed.get("stats") or {}
    status_filter = processed.get("status_filter")
    lines: list[str] = []
    if lang == "en":
        lines.append("**Agent missions**")
        if status_filter:
            lines.append(f"Filter: status={status_filter}")
        if stats:
            lines.append(
                f"Total {stats.get('total', len(items))} — "
                f"running {stats.get('running', 0)}, completed {stats.get('completed', 0)}"
            )
    else:
        lines.append("**Missions agent**")
        if status_filter:
            lines.append(f"Filtre : statut={status_filter}")
        if stats:
            lines.append(
                f"Total {stats.get('total', len(items))} — "
                f"en cours {stats.get('running', 0)}, terminées {stats.get('completed', 0)}"
            )
    if not items:
        lines.append("Aucune mission trouvée." if lang == "fr" else "No missions found.")
        return "\n".join(lines)
    for row in items:
        mid = row.get("id")
        agent = AGENT_LABELS.get(row.get("agent_type", ""), row.get("agent_type", ""))
        status = row.get("status", "")
        desc = (row.get("task_description") or "")[:80]
        lines.append(f"- #{mid} | {agent} | {status} | {desc}")
        lines.append(f"  → {_mission_link(int(mid))}")
    return "\n".join(lines)


def _compose_results(processed: dict[str, Any], lang: str) -> str:
    mission = processed.get("mission") or {}
    results = processed.get("results") or {}
    mid = mission.get("id")
    agent = AGENT_LABELS.get(mission.get("agent_type", ""), mission.get("agent_type", ""))
    status = mission.get("status", "")
    lines = [
        f"**Mission #{mid}** — {agent} ({status})" if lang == "fr" else f"**Mission #{mid}** — {agent} ({status})",
        (mission.get("task_description") or "")[:300],
        "",
    ]
    summary = results.get("executive_summary") or ""
    if summary:
        lines.append(f"**{'Synthèse' if lang == 'fr' else 'Summary'}** — {summary[:600]}")
    metrics = results.get("metrics") or {}
    if metrics:
        bits = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:8])
        lines.append(f"**{'Métriques' if lang == 'fr' else 'Metrics'}** — {bits}")
    step_results = results.get("step_results") or []
    if step_results:
        lines.append("")
        lines.append("**Étapes**" if lang == "fr" else "**Steps**")
        for step in step_results[:6]:
            title = step.get("title") or step.get("action_type") or "step"
            st = step.get("status", "")
            lines.append(f"- {title} — {st}")
    lines.append("")
    lines.append(f"→ {_mission_link(int(mid))}?tab=results")
    return "\n".join(lines)


def _compose_logs_summary(processed: dict[str, Any], lang: str) -> str:
    mission = processed.get("mission") or {}
    summary = processed.get("logs_summary") or {}
    mid = mission.get("id")
    agent = AGENT_LABELS.get(mission.get("agent_type", ""), mission.get("agent_type", ""))
    counts = summary.get("counts") or {}
    lines = [
        f"**Logs mission #{mid}** — {agent}" if lang == "fr" else f"**Mission #{mid} logs** — {agent}",
        f"INFO {counts.get('INFO', 0)} | WARNING {counts.get('WARNING', 0)} | ERROR {counts.get('ERROR', 0)}",
        "",
    ]
    recent = summary.get("recent_issues") or []
    if recent:
        lines.append("**Derniers avertissements / erreurs**" if lang == "fr" else "**Recent warnings / errors**")
        for item in recent:
            lines.append(f"- [{item.get('level')}] {item.get('at', '')} — {(item.get('message') or '')[:120]}")
        lines.append("")
    timeline = summary.get("timeline") or []
    if timeline:
        lines.append("**Timeline**" if lang == "fr" else "**Timeline**")
        for row in timeline:
            excerpt = (row.get("excerpt") or "")[:100]
            lines.append(f"- Étape {row.get('step_order')} — {row.get('status')} — {excerpt}")
        lines.append("")
    lines.append(f"→ {_mission_link(int(mid))}?tab=logs")
    return "\n".join(lines)


def _compose_confirm(processed: dict[str, Any], plan: MissionsPlan, lang: str) -> str:
    mid = plan.mission_id or processed.get("mission", {}).get("id")
    action = plan.task_type.value.replace("mission_", "")
    if lang == "en":
        body = f"Confirm **{action}** for mission #{mid}?"
        marker_hint = "Reply yes or no to confirm this mission action."
    else:
        body = f"Confirmer **{action}** pour la mission #{mid} ?"
        marker_hint = MISSIONS_CONFIRM_MARKER_FR
    return body + "\n\n" + marker_hint + build_missions_pending_marker(
        action=action,
        mission_id=int(mid),
        stage="confirm",
    )


def _compose_confirm_delete(processed: dict[str, Any], plan: MissionsPlan, lang: str) -> str:
    mid = plan.mission_id or processed.get("mission", {}).get("id")
    phrase = f"SUPPRIMER mission #{mid}"
    if lang == "en":
        body = (
            f"Permanent deletion of mission #{mid}. "
            f"Type exactly: **{phrase}**"
        )
    else:
        body = (
            f"Suppression définitive de la mission #{mid}. "
            f"Tapez exactement : **{phrase}**"
        )
    return body + build_missions_pending_marker(
        action="delete",
        mission_id=int(mid),
        stage="delete_phrase",
        expected_phrase=phrase,
    )


def _compose_done(
    processed: dict[str, Any],
    plan: MissionsPlan,
    action_result: dict[str, Any],
    lang: str,
) -> str:
    mission = processed.get("mission") or action_result
    mid = mission.get("id") or plan.mission_id
    status = mission.get("status", "")
    task = plan.task_type
    if task == MissionsTaskType.mission_retry:
        msg = (
            f"Mission #{mid} relancée (statut : {status})."
            if lang == "fr"
            else f"Mission #{mid} restarted (status: {status})."
        )
    elif task == MissionsTaskType.mission_resume:
        msg = (
            f"Mission #{mid} reprise (statut : {status})."
            if lang == "fr"
            else f"Mission #{mid} resumed (status: {status})."
        )
    elif task == MissionsTaskType.mission_cancel:
        msg = (
            f"Mission #{mid} annulée."
            if lang == "fr"
            else f"Mission #{mid} cancelled."
        )
    elif task == MissionsTaskType.mission_delete:
        msg = (
            f"Mission #{mid} supprimée définitivement."
            if lang == "fr"
            else f"Mission #{mid} permanently deleted."
        )
    else:
        msg = f"Mission #{mid} — {status}"
    if mid and task != MissionsTaskType.mission_delete:
        msg += f"\n→ {_mission_link(int(mid))}"
    return msg
