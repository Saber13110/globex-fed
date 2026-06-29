"""Outils de traitement dashboard — validation, priorités, activité (pas de LLM)."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.dashboard.dashboard_anomalies import detect_dashboard_anomalies
from app.services.admin_client.dashboard.dashboard_types import DashboardPlan, DashboardTaskType

_REQUIRED_NUMERIC = (
    "shipments_today",
    "delivered_today",
    "in_transit",
    "delayed_shipments",
    "active_users",
    "total_users",
    "open_incidents",
    "fedex_requests_today",
)

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def validate_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    """Vérifie valeurs manquantes, doublons KPI et incohérences déjà connues."""
    lang = str(data.get("lang") or "fr")
    missing: list[str] = [k for k in _REQUIRED_NUMERIC if data.get(k) is None]
    dq = data.get("data_quality") or {}
    inconsistencies = list(dq.get("inconsistencies") or [])

    duplicate_kpis = False
    seen_labels: set[str] = set()
    for item in data.get("kpi_cards") or []:
        label = str(item.get("label") or "").strip().lower()
        if label and label in seen_labels:
            duplicate_kpis = True
            break
        if label:
            seen_labels.add(label)

    valid = not missing and not inconsistencies and not duplicate_kpis
    return {
        "valid": valid,
        "missing_fields": missing,
        "duplicate_kpis": duplicate_kpis,
        "inconsistencies": inconsistencies,
        "message": (
            "Données dashboard incomplètes ou incohérentes."
            if lang == "fr" and not valid
            else "Dashboard data incomplete or inconsistent."
            if not valid
            else ""
        ),
    }


def classify_dashboard_priorities(
    data: dict[str, Any],
    *,
    anomalies: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Classe les KPI à surveiller en priorité (données réelles uniquement)."""
    lang = str(data.get("lang") or "fr")
    items: list[dict[str, Any]] = []

    def _add(kpi: str, value: Any, priority: str, reason_fr: str, reason_en: str) -> None:
        if value is None:
            return
        items.append(
            {
                "kpi": kpi,
                "value": value,
                "priority": priority,
                "reason": reason_fr if lang == "fr" else reason_en,
            }
        )

    incidents = int(data.get("open_incidents") or 0)
    if incidents > 0:
        _add(
            "open_incidents",
            incidents,
            "critical",
            f"{incidents} incident(s) ouvert(s)",
            f"{incidents} open incident(s)",
        )

    delayed = int(data.get("delayed_shipments") or 0)
    if delayed > 0:
        _add(
            "delayed_shipments",
            delayed,
            "high",
            f"{delayed} colis en retard",
            f"{delayed} delayed shipments",
        )

    blocked = int(data.get("blocked_shipments") or 0)
    if blocked > 0:
        _add(
            "blocked_shipments",
            blocked,
            "high",
            f"{blocked} colis bloqués / exception",
            f"{blocked} blocked shipments",
        )

    err_rate = float(data.get("fedex_error_rate") or 0)
    if err_rate > 0.05:
        _add(
            "fedex_error_rate",
            round(err_rate * 100, 1),
            "high",
            f"Taux d'erreur FedEx API ({round(err_rate * 100, 1)}%)",
            f"FedEx API error rate ({round(err_rate * 100, 1)}%)",
        )

    for h in data.get("system_health") or []:
        if not h.get("operational") or float(h.get("percent") or 100) < 100:
            _add(
                f"system_health:{h.get('key') or h.get('name')}",
                h.get("percent"),
                "high",
                f"Service {h.get('name')} dégradé",
                f"Service {h.get('name')} degraded",
            )

    active = data.get("active_users")
    total = data.get("total_users")
    if active is not None:
        _add(
            "active_users",
            active,
            "medium",
            f"{active} utilisateurs actifs (total {total})",
            f"{active} active users (total {total})",
        )

    shipments = int(data.get("shipments_today") or 0)
    if shipments > 0:
        _add(
            "shipments_today",
            shipments,
            "medium",
            f"{shipments} expéditions suivies aujourd'hui",
            f"{shipments} shipments tracked today",
        )

    fedex_req = int(data.get("fedex_requests_today") or 0)
    if fedex_req == 0 and shipments > 0:
        _add(
            "fedex_requests_today",
            fedex_req,
            "medium",
            "Requêtes FedEx nulles malgré des expéditions actives",
            "Zero FedEx requests despite active shipments",
        )

    for flag in anomalies or []:
        if not any(flag in str(i.get("reason") or "") for i in items):
            items.append(
                {
                    "kpi": "anomaly",
                    "value": None,
                    "priority": "medium",
                    "reason": flag,
                }
            )

    items.sort(key=lambda x: _PRIORITY_ORDER.get(str(x.get("priority")), 9))
    return items[:7]


def summarize_recent_activity(
    data: dict[str, Any],
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Résumé structuré de recent_activity — sans invention."""
    events = list(data.get("recent_activity") or [])
    by_level: dict[str, int] = {}
    for ev in events:
        level = str(ev.get("level") or "INFO").upper()
        by_level[level] = by_level.get(level, 0) + 1
    return {
        "total_events": len(events),
        "by_level": by_level,
        "highlights": events[:limit],
        "has_errors": by_level.get("ERROR", 0) + by_level.get("CRITICAL", 0) > 0,
    }


def process_dashboard_data(data: dict[str, Any], plan: DashboardPlan) -> dict[str, Any]:
    """Enchaîne validate → anomalies → priorités → activité."""
    validation = validate_dashboard_data(data)
    anomalies, data_quality = detect_dashboard_anomalies(data)
    priorities = classify_dashboard_priorities(data, anomalies=anomalies)
    activity = summarize_recent_activity(data, limit=plan.limit)

    enriched = {
        **data,
        "anomalies": anomalies,
        "data_quality": {**(data.get("data_quality") or {}), **data_quality},
        "validation": validation,
        "priorities": priorities,
        "activity_digest": activity,
    }
    return {
        "summary": enriched,
        "validation": validation,
        "anomalies": anomalies,
        "priorities": priorities,
        "activity_digest": activity,
        "tools_run": [
            "validate_dashboard_data",
            "detect_dashboard_anomalies",
            "classify_dashboard_priorities",
            "summarize_recent_activity",
        ],
    }
