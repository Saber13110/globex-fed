"""Règles d'anomalie dashboard — schéma canonique + snapshot legacy."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot

_FEDEX_ERROR_THRESHOLD = 0.05
_DELAY_RATIO_THRESHOLD = 0.20
_ERROR_LOG_THRESHOLD = 3


def detect_dashboard_anomalies(data: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Détecte anomalies et incohérences sur get_dashboard_summary."""
    lang = str(data.get("lang") or "fr")
    flags: list[str] = []
    inconsistencies: list[str] = []

    active = data.get("active_users")
    total = data.get("total_users")
    online = data.get("online_users")

    if active is not None and total is not None and int(active) > int(total):
        msg = (
            f"Incohérence : utilisateurs actifs ({active}) > utilisateurs totaux ({total})"
            if lang == "fr"
            else f"Inconsistency: active users ({active}) > total users ({total})"
        )
        inconsistencies.append(msg)
        flags.append(msg)

    if online is not None and active is not None and int(online) > int(active):
        msg = (
            f"Incohérence : utilisateurs en ligne ({online}) > utilisateurs actifs ({active})"
            if lang == "fr"
            else f"Inconsistency: online users ({online}) > active users ({active})"
        )
        inconsistencies.append(msg)
        flags.append(msg)

    open_incidents = int(data.get("open_incidents") or 0)
    if open_incidents > 0:
        flags.append(
            f"{open_incidents} incident(s) ouvert(s)"
            if lang == "fr"
            else f"{open_incidents} open incident(s)"
        )

    error_rate = float(data.get("fedex_error_rate") or 0)
    if error_rate > _FEDEX_ERROR_THRESHOLD:
        pct = round(error_rate * 100, 1)
        flags.append(
            f"Taux d'erreur FedEx API élevé ({pct}%)"
            if lang == "fr"
            else f"High FedEx API error rate ({pct}%)"
        )

    delayed = int(data.get("delayed_shipments") or 0)
    shipments_today = int(data.get("shipments_today") or 0)
    if shipments_today and delayed / shipments_today > _DELAY_RATIO_THRESHOLD:
        flags.append(
            f"Pic de retards ({delayed}/{shipments_today} colis)"
            if lang == "fr"
            else f"Delay spike ({delayed}/{shipments_today} shipments)"
        )

    blocked = int(data.get("blocked_shipments") or 0)
    if blocked > 0:
        flags.append(
            f"{blocked} colis bloqués / exception"
            if lang == "fr"
            else f"{blocked} blocked / exception shipments"
        )

    if delayed > 0 and not any("retard" in f.lower() or "delay" in f.lower() for f in flags):
        flags.append(
            f"{delayed} colis en retard"
            if lang == "fr"
            else f"{delayed} delayed shipments"
        )

    fedex_req = int(data.get("fedex_requests_today") or 0)
    if fedex_req == 0 and shipments_today > 0:
        flags.append(
            "Requêtes FedEx nulles malgré des expéditions actives"
            if lang == "fr"
            else "Zero FedEx requests despite active shipments"
        )

    err_count = sum(
        1
        for a in data.get("recent_activity") or []
        if str(a.get("level") or "").upper() in ("ERROR", "CRITICAL")
    )
    if err_count >= _ERROR_LOG_THRESHOLD:
        flags.append(
            f"{err_count} entrée(s) ERROR dans l'activité récente"
            if lang == "fr"
            else f"{err_count} ERROR entries in recent activity"
        )

    pending = int(data.get("pending_invitations") or 0)
    if pending > 0:
        flags.append(
            f"{pending} invitation(s) employé en attente"
            if lang == "fr"
            else f"{pending} pending employee invitation(s)"
        )

    for h in data.get("system_health") or []:
        if not h.get("operational"):
            flags.append(
                f"Service {h.get('name')} non opérationnel"
                if lang == "fr"
                else f"Service {h.get('name')} not operational"
            )
        elif float(h.get("percent") or 100) < 100:
            flags.append(
                f"Service {h.get('name')} à {float(h.get('percent')):.0f}%"
                if lang == "fr"
                else f"Service {h.get('name')} at {float(h.get('percent')):.0f}%"
            )

    data_quality = {
        "duplicate_kpis": False,
        "inconsistencies": inconsistencies,
        "has_inconsistency": bool(inconsistencies),
    }
    return flags, data_quality


def detect_anomalies(snapshot: DashboardSnapshot) -> list[str]:
    """Legacy — délègue au schéma canonique si summary présent."""
    if snapshot.summary:
        flags, _ = detect_dashboard_anomalies(snapshot.summary)
        return flags

    cc = snapshot.command_center
    lang = snapshot.lang
    flags: list[str] = []

    if cc.open_incidents > 0:
        flags.append(
            f"{cc.open_incidents} incident(s) sécurité ouvert(s)"
            if lang == "fr"
            else f"{cc.open_incidents} open security incident(s)"
        )

    if cc.fedex_metrics.error_rate > _FEDEX_ERROR_THRESHOLD:
        pct = round(cc.fedex_metrics.error_rate * 100, 1)
        flags.append(
            f"Taux d'erreur FedEx API élevé ({pct}%)"
            if lang == "fr"
            else f"High FedEx API error rate ({pct}%)"
        )

    total_ship = len(cc.live_shipments)
    if total_ship and len(snapshot.delayed_shipments) / total_ship > _DELAY_RATIO_THRESHOLD:
        flags.append(
            f"Pic de retards ({len(snapshot.delayed_shipments)}/{total_ship} colis)"
            if lang == "fr"
            else f"Delay spike ({len(snapshot.delayed_shipments)}/{total_ship} shipments)"
        )

    err_count = snapshot.activity_level_counts.get("ERROR", 0)
    if err_count >= _ERROR_LOG_THRESHOLD:
        flags.append(
            f"{err_count} entrée(s) ERROR dans l'activité récente"
            if lang == "fr"
            else f"{err_count} ERROR entries in recent activity"
        )

    if cc.pending_invitations > 0:
        flags.append(
            f"{cc.pending_invitations} invitation(s) employé en attente"
            if lang == "fr"
            else f"{cc.pending_invitations} pending employee invitation(s)"
        )

    for h in cc.system_health:
        if not h.operational:
            flags.append(
                f"Service {h.name} non opérationnel"
                if lang == "fr"
                else f"Service {h.name} not operational"
            )

    return flags
