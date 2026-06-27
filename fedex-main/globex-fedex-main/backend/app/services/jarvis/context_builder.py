"""Contexte plateforme Globex (lecture seule) injecté avant l'appel Jarvis."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.security_incident import SecurityIncident
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.user import User, UserStatus
from app.services.command_center_service import build_command_center


def build_globex_context_block(db: Session, admin: User) -> str:
    """Résumé KPI compact pour le prompt Jarvis."""
    settings = get_settings()
    if not settings.jarvis_inject_context:
        return ""

    cc = build_command_center(db)
    open_tickets = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status.in_((SupportTicketStatus.open, SupportTicketStatus.pending)))
        )
        or 0
    )
    active_users = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.active.value)
        )
        or 0
    )
    suspended = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.suspended.value)
        )
        or 0
    )
    open_security = int(
        db.scalar(
            select(func.count())
            .select_from(SecurityIncident)
            .where(SecurityIncident.status == "open")
        )
        or 0
    )

    shipments_today = cc.hero_stats[0].value if cc.hero_stats else "n/a"
    active_sessions = cc.hero_stats[2].value if len(cc.hero_stats) > 2 else "n/a"

    lines = [
        "[CONTEXTE GLOBEX FEDEX — lecture seule, ne pas inventer au-delà]",
        f"- Admin connecté : {admin.full_name} ({admin.email})",
        f"- Utilisateurs actifs : {active_users} | suspendus : {suspended}",
        f"- Sessions actives (dashboard) : {active_sessions}",
        f"- Expéditions / tracking (indicateur) : {shipments_today}",
        f"- Tickets support ouverts/en attente : {open_tickets}",
        f"- Incidents plateforme ouverts : {cc.open_incidents} | IDS ouverts : {open_security}",
        f"- Requêtes FedEx API aujourd'hui : {cc.fedex_metrics.requests_today if cc.fedex_metrics else 'n/a'}",
        "- Actions destructrices (suspendre, exporter, e-mail) : utiliser l'onglet **Jarvis** en **mode Agent** — "
        "[FIN CONTEXTE]",
    ]
    text = "\n".join(lines)
    max_chars = max(500, settings.jarvis_context_max_chars)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n[… tronqué]"
    return text
