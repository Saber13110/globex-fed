"""Graphiques matplotlib pour le rapport quotidien client."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.client_phase8.daily_report_collector import DailyReportSnapshot

_CHART_LABELS = {
    "fr": {
        "hourly": "Activité par heure",
        "status": "Statuts colis",
        "notif": "Notifications (type)",
        "messages_trackings": "Messages + colis",
    },
    "en": {
        "hourly": "Activity by hour",
        "status": "Shipment status",
        "notif": "Notifications (type)",
        "messages_trackings": "Messages + trackings",
    },
}


def _setup_agg() -> None:
    import matplotlib

    matplotlib.use("Agg")


def _status_label(key: str, lang: str) -> str:
    from app.services.client_phase8.daily_report_collector import _STATUS_LABELS

    labels = _STATUS_LABELS.get(lang, _STATUS_LABELS["fr"])
    return labels.get(key, key.replace("_", " ").title())


def render_daily_report_charts(snapshot: "DailyReportSnapshot") -> dict[str, bytes]:
    """Retourne {chart_key: png_bytes} pour les graphiques du rapport."""
    _setup_agg()
    import matplotlib.pyplot as plt

    lang = snapshot.lang
    labels = _CHART_LABELS.get(lang, _CHART_LABELS["fr"])
    out: dict[str, bytes] = {}

    # Activité par heure
    hours = list(range(0, 24))
    values = [snapshot.hourly_activity.get(h, 0) for h in hours]
    if any(values):
        fig, ax = plt.subplots(figsize=(7, 3.2))
        ax.bar(hours, values, color="#4A5568", width=0.8)
        ax.set_xlabel("Heure" if lang == "fr" else "Hour")
        ax.set_ylabel(labels["messages_trackings"])
        ax.set_title(labels["hourly"])
        ax.set_xticks([0, 6, 12, 18, 23])
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["hourly"] = buf.getvalue()

    # Statuts colis
    if snapshot.shipment_status_counts:
        keys = list(snapshot.shipment_status_counts.keys())
        vals = [snapshot.shipment_status_counts[k] for k in keys]
        fig, ax = plt.subplots(figsize=(4.5, 4.5))
        ax.pie(
            vals,
            labels=[_status_label(k, lang) for k in keys],
            autopct="%1.0f%%",
            startangle=90,
        )
        ax.set_title(labels["status"])
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["status"] = buf.getvalue()

    # Notifications par type
    if snapshot.notification_type_counts:
        keys = list(snapshot.notification_type_counts.keys())[:8]
        vals = [snapshot.notification_type_counts[k] for k in keys]
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.barh(keys, vals, color="#2B6CB0")
        ax.set_title(labels["notif"])
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["notifications"] = buf.getvalue()

    return out
