"""Graphiques matplotlib dashboard admin."""

from __future__ import annotations

from io import BytesIO

from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot

_COLORS = {
    "in_transit": "#7C3AED",
    "delivered": "#22C55E",
    "delayed": "#FF6A00",
    "INFO": "#3B82F6",
    "WARNING": "#FF6A00",
    "ERROR": "#EF4444",
}


def _setup_agg() -> None:
    import matplotlib

    matplotlib.use("Agg")


def render_dashboard_charts(snapshot: DashboardSnapshot) -> dict[str, bytes]:
    """Retourne {chart_key: png_bytes}."""
    try:
        _setup_agg()
        import matplotlib.pyplot as plt
    except ImportError:
        return {}

    lang = snapshot.lang
    cc = snapshot.command_center
    out: dict[str, bytes] = {}

    counts = snapshot.shipment_status_counts
    if counts:
        keys = list(counts.keys())
        vals = [counts[k] for k in keys]
        colors = [_COLORS.get(k, "#7C3AED") for k in keys]
        fig, ax = plt.subplots(figsize=(4.5, 4.5))
        ax.pie(vals, labels=keys, autopct="%1.0f%%", colors=colors, startangle=90)
        ax.set_title("Statuts colis" if lang == "fr" else "Shipment status")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["shipment_status"] = buf.getvalue()

    series = cc.fedex_metrics.requests_series
    if series:
        labels = [p.label for p in series]
        vals = [p.value for p in series]
        fig, ax = plt.subplots(figsize=(7, 3.2))
        ax.bar(labels, vals, color="#7C3AED", width=0.7)
        ax.set_title("Requêtes FedEx (7j)" if lang == "fr" else "FedEx requests (7d)")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["fedex_requests_7d"] = buf.getvalue()

    if snapshot.users_by_role:
        roles = list(snapshot.users_by_role.keys())
        vals = [snapshot.users_by_role[r] for r in roles]
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.barh(roles, vals, color="#3B82F6")
        ax.set_title("Utilisateurs par rôle" if lang == "fr" else "Users by role")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["user_roles"] = buf.getvalue()

    if snapshot.activity_level_counts:
        keys = list(snapshot.activity_level_counts.keys())
        vals = [snapshot.activity_level_counts[k] for k in keys]
        colors = [_COLORS.get(k, "#7C3AED") for k in keys]
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.bar(keys, vals, color=colors)
        ax.set_title("Niveaux activité" if lang == "fr" else "Activity levels")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["activity_levels"] = buf.getvalue()

    delayed = snapshot.delayed_shipments[:8]
    if delayed:
        labels = [s.tracking_number[-6:] for s in delayed]
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.barh(labels, [1] * len(labels), color="#FF6A00")
        ax.set_title("Retards" if lang == "fr" else "Delays")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        out["delayed_top"] = buf.getvalue()

    return out
