"""Composeur de réponse dashboard — profils SUMMARY / STATUS / KPI / LIST / EXPLAIN."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.dashboard.dashboard_types import DashboardPlan, DashboardTaskType
from app.services.admin_client.dashboard.dashboard_reconcile import DashboardQuestionType
from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot

_SOURCE_FOOTER_FR = "\n\n_Source : Dashboard Admin_"
_SOURCE_FOOTER_EN = "\n\n_Source: Admin Dashboard_"


def _na(val: Any, lang: str) -> str:
    if val is None:
        return "donnée non disponible" if lang == "fr" else "data not available"
    return str(val)


def _summary_data(snapshot: DashboardSnapshot) -> dict[str, Any]:
    if snapshot.summary:
        return snapshot.summary
    cc = snapshot.command_center
    return {
        "shipments_today": len(cc.live_shipments),
        "delivered_today": None,
        "in_transit": None,
        "delayed_shipments": len(snapshot.delayed_shipments),
        "active_users": cc.total_users,
        "total_users": cc.total_users,
        "online_users": cc.online_users,
        "open_incidents": cc.open_incidents,
        "fedex_requests_today": cc.fedex_metrics.requests_today,
        "fedex_error_rate": cc.fedex_metrics.error_rate,
        "system_health": [
            {"name": h.name, "percent": h.percent, "operational": h.operational}
            for h in cc.system_health
        ],
        "recent_activity": [
            {"time_label": a.time_label, "level": a.level, "message": a.message}
            for a in cc.activity_timeline
        ],
        "anomalies": snapshot.anomaly_flags,
        "data_quality": {},
    }


def _kpi_lines(d: dict[str, Any], lang: str) -> list[str]:
    if lang == "en":
        pairs = [
            ("Shipments today", d.get("shipments_today")),
            ("Delivered", d.get("delivered_today")),
            ("In transit", d.get("in_transit")),
            ("Active users", d.get("active_users")),
            ("Total users", d.get("total_users")),
            ("Online users", d.get("online_users")),
            ("Open incidents", d.get("open_incidents")),
            ("FedEx requests today", d.get("fedex_requests_today")),
        ]
    else:
        pairs = [
            ("Expéditions aujourd'hui", d.get("shipments_today")),
            ("Livraisons complétées", d.get("delivered_today")),
            ("En transit", d.get("in_transit")),
            ("Utilisateurs actifs", d.get("active_users")),
            ("Utilisateurs totaux", d.get("total_users")),
            ("Utilisateurs en ligne", d.get("online_users")),
            ("Incidents ouverts", d.get("open_incidents")),
            ("Requêtes FedEx aujourd'hui", d.get("fedex_requests_today")),
        ]
    return [f"- **{label}** : {_na(val, lang)}" for label, val in pairs]


def compose_summary_profile(d: dict[str, Any], lang: str) -> str:
    if lang == "en":
        parts = [
            "**Global summary**",
            "",
            f"Platform snapshot: { _na(d.get('shipments_today'), lang) } shipments tracked today, "
            f"{ _na(d.get('open_incidents'), lang) } open incidents, "
            f"{ _na(d.get('active_users'), lang) } active users.",
            "",
            "**Key figures**",
            "",
            *_kpi_lines(d, lang),
        ]
    else:
        parts = [
            "**Résumé global**",
            "",
            f"Snapshot plateforme : { _na(d.get('shipments_today'), lang) } expéditions suivies aujourd'hui, "
            f"{ _na(d.get('open_incidents'), lang) } incidents ouverts, "
            f"{ _na(d.get('active_users'), lang) } utilisateurs actifs.",
            "",
            "**Chiffres clés**",
            "",
            *_kpi_lines(d, lang),
        ]
    anomalies = d.get("anomalies") or []
    if anomalies:
        parts.extend(["", "**Anomalies / points à surveiller :**" if lang == "fr" else "**Anomalies / watch points:**"])
        parts.extend(f"- {a}" for a in anomalies)
    dq = d.get("data_quality") or {}
    for inc in dq.get("inconsistencies") or []:
        parts.append(f"- ⚠ {inc}")
    return "\n".join(parts)


def compose_status_profile(d: dict[str, Any], lang: str) -> str:
    anomalies = d.get("anomalies") or []
    incidents = int(d.get("open_incidents") or 0)
    delayed = int(d.get("delayed_shipments") or 0)
    health_bad = [
        h for h in d.get("system_health") or []
        if not h.get("operational") or float(h.get("percent") or 100) < 100
    ]
    has_issue = bool(anomalies or incidents or delayed or health_bad)

    if lang == "en":
        verdict = "**Partial issues detected.**" if has_issue else "**No major issue detected.**"
        parts = ["**Platform health check**", "", verdict, ""]
    else:
        verdict = "**Problèmes partiels détectés.**" if has_issue else "**Aucun problème majeur détecté.**"
        parts = ["**Contrôle santé plateforme**", "", verdict, ""]

    if incidents:
        parts.append(f"- {incidents} open incident(s)")
    if delayed:
        parts.append(f"- {delayed} delayed shipment(s)" if lang == "en" else f"- {delayed} colis en retard")
    for h in health_bad:
        parts.append(f"- {h.get('name')}: {h.get('percent')}%")
    for a in anomalies[:6]:
        parts.append(f"- {a}")
    if not has_issue:
        parts.append(
            "All monitored services are operational."
            if lang == "en"
            else "Les services surveillés sont opérationnels."
        )
    return "\n".join(parts)


def compose_kpi_list_profile(d: dict[str, Any], lang: str) -> str:
    title = "**Main KPIs**" if lang == "en" else "**KPIs principaux**"
    priorities = d.get("priorities") or []
    if priorities:
        lines = [title, ""]
        for p in priorities[:7]:
            val = p.get("value")
            reason = str(p.get("reason") or p.get("kpi") or "")
            if val is not None:
                lines.append(f"- **{p.get('kpi')}** : {_na(val, lang)} — {reason}")
            else:
                lines.append(f"- {reason}")
        return "\n".join(lines)
    return "\n".join([title, ""] + _kpi_lines(d, lang)[:7])


def compose_list_activity(d: dict[str, Any], plan: DashboardPlan, lang: str) -> str:
    title = "**Recent activity**" if lang == "en" else "**Activité récente**"
    digest = d.get("activity_digest") or {}
    items = list(digest.get("highlights") or d.get("recent_activity") or [])[: plan.limit]
    if not items:
        return title + "\n\n" + ("No recent activity." if lang == "en" else "Aucune activité récente.")
    lines = [title, ""]
    for a in items:
        lines.append(f"- `{a.get('time_label', '—')}` [{a.get('level', 'INFO')}] {a.get('message', '')}")
    return "\n".join(lines)


def compose_explain_profile(d: dict[str, Any], lang: str) -> str:
    if lang == "en":
        return (
            "**Dashboard statistics explained**\n\n"
            f"- **Shipments today** counts tracked packages ({_na(d.get('shipments_today'), lang)}).\n"
            f"- **Delivered / in transit** split fulfillment ({_na(d.get('delivered_today'), lang)} / "
            f"{_na(d.get('in_transit'), lang)}).\n"
            f"- **Users** active vs total ({_na(d.get('active_users'), lang)} / "
            f"{_na(d.get('total_users'), lang)}).\n"
            f"- **Incidents** open tickets/security ({_na(d.get('open_incidents'), lang)}).\n"
            f"- **FedEx API** requests today ({_na(d.get('fedex_requests_today'), lang)})."
        )
    return (
        "**Statistiques dashboard expliquées**\n\n"
        f"- **Expéditions aujourd'hui** : colis suivis ({_na(d.get('shipments_today'), lang)}).\n"
        f"- **Livré / en transit** : répartition ({_na(d.get('delivered_today'), lang)} / "
        f"{_na(d.get('in_transit'), lang)}).\n"
        f"- **Utilisateurs** actifs vs total ({_na(d.get('active_users'), lang)} / "
        f"{_na(d.get('total_users'), lang)}).\n"
        f"- **Incidents** ouverts ({_na(d.get('open_incidents'), lang)}).\n"
        f"- **API FedEx** requêtes du jour ({_na(d.get('fedex_requests_today'), lang)})."
    )


def compose_delayed_list(snapshot: DashboardSnapshot, plan: DashboardPlan, lang: str) -> str:
    d = _summary_data(snapshot)
    details = d.get("delayed_shipments_detail") or []
    if not details and snapshot.delayed_shipments:
        details = [
            {
                "tracking_number": s.tracking_number,
                "status": s.status,
                "route": s.route,
                "eta_label": s.eta_label,
            }
            for s in snapshot.delayed_shipments[: plan.limit]
        ]
    title = f"**Delayed shipments ({len(details)})**" if lang == "en" else f"**Colis en retard ({len(details)})**"
    if not details:
        return title + "\n\n" + ("None detected." if lang == "en" else "Aucun détecté.")
    lines = [title, ""]
    for s in details[: plan.limit]:
        lines.append(
            f"- **{s.get('tracking_number')}** — {s.get('status')} — {s.get('route')} ({s.get('eta_label')})"
        )
    return "\n".join(lines)


def compose_dashboard_response(
    snapshot: DashboardSnapshot,
    plan: DashboardPlan,
) -> str:
    lang = snapshot.lang
    d = _summary_data(snapshot)
    qtype = plan.question_type
    task = plan.task_type

    if task == DashboardTaskType.delayed_shipments:
        body = compose_delayed_list(snapshot, plan, lang)
    elif task == DashboardTaskType.recent_activity:
        body = compose_list_activity(d, plan, lang)
    elif task == DashboardTaskType.recent_audit:
        if plan.suspicious_only:
            suspicious = [
                a for a in d.get("recent_activity") or []
                if str(a.get("level", "")).upper() in ("WARNING", "ERROR", "CRITICAL")
            ]
            d = {**d, "recent_activity": suspicious}
        body = compose_list_activity(d, plan, lang)
    elif task == DashboardTaskType.users_breakdown:
        title = "**Users breakdown**" if lang == "en" else "**Répartition utilisateurs**"
        lines = [title, "", "**By role:**" if lang == "en" else "**Par rôle :**"]
        for role, count in sorted((d.get("users_by_role") or snapshot.users_by_role).items()):
            lines.append(f"- {role}: **{count}**")
        lines.append("")
        lines.append("**By status:**" if lang == "en" else "**Par statut :**")
        for status, count in sorted((d.get("users_by_status") or snapshot.users_by_status).items()):
            lines.append(f"- {status}: **{count}**")
        body = "\n".join(lines)
    elif task == DashboardTaskType.new_users_period:
        title = "**New users**" if lang == "en" else "**Nouveaux utilisateurs**"
        users = d.get("new_users") or []
        if not users:
            body = title + "\n\n" + ("None on this period." if lang == "en" else "Aucun sur la période.")
        else:
            body = title + "\n\n" + "\n".join(
                f"- **{u.get('full_name')}** ({u.get('email')}) — {u.get('role')}" for u in users[: plan.limit]
            )
    elif task == DashboardTaskType.quick_delay_report:
        body = compose_summary_profile(d, lang) + "\n\n" + compose_delayed_list(snapshot, plan, lang)
    elif qtype == DashboardQuestionType.STATUS:
        body = compose_status_profile(d, lang)
    elif qtype == DashboardQuestionType.KPI_LIST:
        body = compose_kpi_list_profile(d, lang)
    elif qtype == DashboardQuestionType.EXPLAIN:
        body = compose_explain_profile(d, lang)
    elif qtype == DashboardQuestionType.LIST:
        body = compose_list_activity(d, plan, lang)
    else:
        body = compose_summary_profile(d, lang)

    footer = _SOURCE_FOOTER_EN if lang == "en" else _SOURCE_FOOTER_FR
    return body + footer
