"""Réponses déterministes Security IDS admin."""

from __future__ import annotations

import json
from typing import Any

from app.services.admin_client.security.security_types import SecurityPlan, SecurityProfile


def compose_security_response(
    processed: dict[str, Any],
    plan: SecurityPlan,
    *,
    lang: str = "fr",
    error_code: str | None = None,
) -> str:
    if error_code:
        return _error_text(error_code, lang)
    if plan.profile == SecurityProfile.LIST:
        return _compose_list(processed, plan, lang)
    if plan.profile == SecurityProfile.DETAIL:
        return _compose_detail(processed, lang)
    if plan.profile == SecurityProfile.SUMMARY:
        return _compose_summary(processed, lang)
    if plan.profile == SecurityProfile.SCAN:
        return _compose_scan(processed, lang)
    if plan.profile == SecurityProfile.REPORT:
        return _compose_report(processed, lang)
    if plan.profile == SecurityProfile.CLARIFY:
        return plan.clarification_question or default_clarify(lang)
    return _compose_list(processed, plan, lang)


def default_clarify(lang: str) -> str:
    if lang == "en":
        return "Could you clarify your security IDS request?"
    return "Pouvez-vous préciser votre demande sur la sécurité IDS ?"


def _error_text(code: str, lang: str) -> str:
    catalog_fr = {
        "incident_not_found": "Incident sécurité introuvable.",
        "fetch_failed": "Impossible de récupérer les données sécurité en temps réel.",
        "scan_failed": "Échec du scan IDS.",
    }
    catalog_en = {
        "incident_not_found": "Security incident not found.",
        "fetch_failed": "Could not fetch live security data.",
        "scan_failed": "IDS scan failed.",
    }
    catalog = catalog_en if lang == "en" else catalog_fr
    label = "Erreur" if lang == "fr" else "Error"
    return f"**{label}** — {catalog.get(code, code)}"


def _filter_bits(plan: SecurityPlan, lang: str) -> list[str]:
    bits: list[str] = []
    if plan.status_filter:
        bits.append(f"statut={plan.status_filter}" if lang == "fr" else f"status={plan.status_filter}")
    if plan.severity_filter:
        bits.append(f"sévérité={plan.severity_filter}" if lang == "fr" else f"severity={plan.severity_filter}")
    return bits


def _escape_cell(value: str) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")[:80]


def _compose_list(processed: dict[str, Any], plan: SecurityPlan, lang: str) -> str:
    incidents = processed.get("incidents") or []
    title = "**Incidents sécurité**" if lang == "fr" else "**Security incidents**"
    filter_bits = _filter_bits(plan, lang)
    header = title + (f" ({', '.join(filter_bits)})" if filter_bits else "")

    if not incidents:
        empty = (
            "Aucun incident ne correspond aux filtres."
            if lang == "fr"
            else "No incidents match the filters."
        )
        return f"{header}\n\n{empty}"

    open_count = processed.get("open_count", 0)
    total = processed.get("total", len(incidents))
    lines = [
        header,
        "",
        f"{'Affichés' if lang == 'fr' else 'Shown'} : **{len(incidents)}** / {total}"
        + (f" — **{open_count}** ouverts (open+ack)" if lang == "fr" else f" — **{open_count}** open (open+ack)"),
        "",
        "| # | Date | Sévérité | Menace | Statut | Utilisateur | Titre |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in incidents:
        created = str(row.get("created_at", ""))[:19]
        user = row.get("user_email") or "—"
        title_cell = _escape_cell(str(row.get("title") or "—")[:60])
        lines.append(
            f"| {row.get('id')} | {created} | {row.get('severity', '—')} | "
            f"`{row.get('threat_type', '—')}` | {row.get('status', '—')} | {user} | {title_cell} |"
        )
    hint = (
        "\n\n_Indice : `incident #id` = ID en base ; « le N » ou « #N » = Nᵉ ligne._"
        if lang == "fr"
        else "\n\n_Tip: `incident #id` = database ID; row N or bare #N = Nth line._"
    )
    return "\n".join(lines) + hint


def _compose_detail(processed: dict[str, Any], lang: str) -> str:
    row = processed.get("incident") or {}
    title = "**Fiche incident**" if lang == "fr" else "**Incident detail**"
    evidence = row.get("evidence") or {}
    lines = [
        title,
        "",
        f"**#{row.get('id')}** — {row.get('title', '—')}",
        f"Sévérité : **{row.get('severity', '—')}** | Score : {row.get('score', '—')} | Statut : **{row.get('status', '—')}**",
        f"Menace : `{row.get('threat_type', '—')}` | Source : {row.get('source', '—')}",
        f"Date : {str(row.get('created_at', ''))[:19]} | IP : {row.get('ip_address') or '—'}",
        f"Utilisateur : {row.get('user_name', '—')} ({row.get('user_email') or '—'}) — statut compte : {row.get('user_status') or '—'}",
        f"Action recommandée : **{row.get('recommended_action', '—')}**",
        "",
        f"**Résumé** : {(row.get('summary') or '—')[:800]}",
    ]
    if evidence:
        lines.extend([
            "",
            "**Preuves** :",
            f"```json\n{json.dumps(evidence, ensure_ascii=False, indent=2)[:1200]}\n```",
        ])
    if row.get("resolution_note"):
        lines.append(f"\n**Note résolution** : {row.get('resolution_note')[:400]}")
    return "\n".join(lines)


def _compose_summary(processed: dict[str, Any], lang: str) -> str:
    s = processed.get("summary") or processed
    title = (
        "**Résumé incidents sécurité (ouverts)**"
        if lang == "fr"
        else "**Open security incidents summary**"
    )
    lines = [
        title,
        "",
        f"**Actifs** : {s.get('total_active', s.get('open_count', 0))}"
        if lang == "fr"
        else f"**Active** : {s.get('total_active', s.get('open_count', 0))}",
        f"**Ouverts (open+ack)** : {s.get('open_count', 0)}",
    ]
    if s.get("by_severity"):
        label = "Par sévérité" if lang == "fr" else "By severity"
        lines.append(f"**{label}** : {', '.join(f'{k}: {v}' for k, v in s['by_severity'].items())}")
    if s.get("by_threat"):
        label = "Par menace" if lang == "fr" else "By threat"
        items = list(s["by_threat"].items())[:6]
        lines.append(f"**{label}** : {', '.join(f'`{k}`: {v}' for k, v in items)}")
    critical = s.get("critical_samples") or []
    if critical:
        lines.append("\n**Prioritaires :**" if lang == "fr" else "\n**Priority:**")
        for row in critical[:5]:
            lines.append(
                f"- #{row.get('id')} [{row.get('severity')}] `{row.get('threat_type')}` — "
                f"{_escape_cell(str(row.get('title') or ''))}"
            )
    return "\n".join(lines)


def _compose_scan(processed: dict[str, Any], lang: str) -> str:
    scan = processed.get("scan") or processed
    title = "**Scan IDS terminé**" if lang == "fr" else "**IDS scan completed**"
    ai_note = (
        f" (IA incluse)" if scan.get("include_ai") and lang == "fr"
        else f" (AI included)" if scan.get("include_ai")
        else ""
    )
    lines = [
        title + ai_note,
        "",
        f"- Incidents créés (règles) : **{scan.get('rules_incidents', 0)}**",
        f"- Incidents créés (IA) : **{scan.get('ai_incidents', 0)}**",
        f"- Incidents ouverts actuellement : **{scan.get('open_count', 0)}**",
    ]
    if lang == "fr":
        lines.append("\n_Demandez « liste incidents ouverts » ou « rapport sécurité » pour la suite._")
    else:
        lines.append("\n_Ask for « list open incidents » or « security report » next._")
    return "\n".join(lines)


def _compose_report(processed: dict[str, Any], lang: str) -> str:
    r = processed.get("report") or processed
    title = "**Rapport sécurité**" if lang == "fr" else "**Security report**"
    lines = [
        title,
        "",
        f"**Incidents ouverts** : {r.get('open_incidents_count', 0)}",
        f"**Critiques / élevés** : {r.get('critical_count', 0)}",
        f"**Niveau de risque** : {r.get('risk_level', '—')}",
        f"**Échecs login ({r.get('period_hours', 24)}h)** : {r.get('login_failures', 0)}",
        f"**Tentatives attaque** : {r.get('attack_attempts', 0)}",
        "",
        "**Recommandations :**" if lang == "fr" else "**Recommendations:**",
    ]
    for rec in (r.get("recommendations") or [])[:5]:
        lines.append(f"- {rec}")
    return "\n".join(lines)
