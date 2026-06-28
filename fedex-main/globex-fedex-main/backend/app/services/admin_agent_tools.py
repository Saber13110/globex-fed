"""Outils exécutables pour les missions agent admin (mains de l'agent)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.agent_mission import AgentMission
from app.models.agent_mission_step import AgentMissionStep
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.platform_notification import PlatformNotification
from app.models.security_incident import SecurityIncident
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.support_ticket_message import SupportTicketMessage
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole, UserStatus
from app.services.chat_export_service import generate_tracking_excel_bytes
from app.services.email_service import is_email_configured, send_email_with_attachment
from app.services.employee_notification_service import notify_employee_ticket_admin_reply
from app.services.user_notification_service import create_user_notification
from app.services.activity_log_service import write_log

TRACKING_NUMBER_RE = re.compile(r"\b(\d{12,14})\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
TICKET_ID_RE = re.compile(r"(?:ticket|#)\s*#?(\d+)", re.I)

SENSITIVE_TOOLS = frozenset(
    {
        "suspend_user",
        "reactivate_user",
        "send_email_with_attachment",
        "send_platform_notification",
        "delete_user",
        "suspend_all_active",
        "reply_support_ticket",
        "reactivate_all_suspended",
    }
)

ADMIN_TOOL_LABELS: dict[str, str] = {
    "analyze_only": "Analyse",
    "reactivate_user": "Réactiver compte",
    "reactivate_all_suspended": "Réactiver tous les comptes suspendus",
    "suspend_user": "Suspendre compte",
    "suspend_all_active": "Suspendre tous les comptes actifs",
    "export_tracking_excel": "Export Excel tracking",
    "send_email_with_attachment": "Envoyer e-mail avec pièce jointe",
    "export_and_email_tracking": "Export Excel + e-mail",
    "daily_behavior_report": "Rapport comportement 24h",
    "analyze_tickets": "Analyser tickets",
    "reply_support_ticket": "Répondre au ticket support",
    "analyze_notifications": "Analyser notifications",
    "analyze_logs": "Analyser journaux",
    "export_activity_logs_pdf": "Export PDF des logs",
    "export_activity_logs_excel": "Export Excel des logs",
    "generate_summary": "Synthèse globale",
}


def extract_tracking_numbers(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in TRACKING_NUMBER_RE.findall(text or ""):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def extract_email(text: str) -> str | None:
    m = EMAIL_RE.search(text or "")
    return m.group(0) if m else None


def admin_find_tracking_rows(db: Session, tracking_numbers: list[str]) -> list[TrackingRequest]:
    if not tracking_numbers:
        return []
    rows = list(
        db.scalars(
            select(TrackingRequest)
            .where(TrackingRequest.tracking_number.in_(tracking_numbers))
            .order_by(TrackingRequest.created_at.desc())
        ).all()
    )
    by_tn: dict[str, TrackingRequest] = {}
    for row in rows:
        if row.tracking_number not in by_tn:
            by_tn[row.tracking_number] = row
    return [by_tn[n] for n in tracking_numbers if n in by_tn]


def parse_tracking_intent(task: str) -> str:
    t = (task or "").lower()
    wants_excel = any(k in t for k in ("excel", "xlsx", "export", "fichier", "génér", "gener"))
    wants_mail = any(k in t for k in ("envoy", "mail", "email", "envoi", "envoie"))
    if wants_excel and wants_mail:
        return "export_and_email_tracking"
    if wants_excel:
        return "export_tracking_excel"
    if wants_mail:
        return "export_and_email_tracking"
    return "analyze_tracking"


def parse_users_intent(task: str) -> str:
    t = (task or "").lower()
    bulk = is_bulk_users_task(task)
    if re.search(r"\b(r[eé]activ|restaur|d[eé]bloqu)", t):
        if bulk or (re.search(r"\b(tous|toutes|all)\b", t) and re.search(r"\b(suspendu|suspendus|bloqu)", t)):
            return "reactivate_all_suspended"
        return "reactivate_user"
    if re.search(r"\b(suspend|suspendre|bloqu|d[eé]sactiv)", t):
        if bulk:
            return "suspend_all_active"
        return "suspend_user"
    return "analyze_users"


def is_bulk_users_task(task: str) -> bool:
    t = (task or "").lower()
    return any(k in t for k in ("tous", "toutes", "all", "chaque", "l'ensemble", "ensemble des", "l ensemble"))


def list_suspended_non_admin_users(db: Session, *, limit: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.status == UserStatus.suspended.value,
                User.role != UserRole.admin.value,
            )
            .order_by(User.created_at.desc())
            .limit(limit)
        ).all()
    )


def list_active_non_admin_users(db: Session, *, limit: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.status == UserStatus.active.value,
                User.role != UserRole.admin.value,
            )
            .order_by(User.created_at.desc())
            .limit(limit)
        ).all()
    )


def detect_forced_admin_tool(task: str) -> str | None:
    """Détection déterministe — prioritaire sur le plan Gemini."""
    t = (task or "").lower()
    has_logs = bool(re.search(r"\blog", t)) or any(k in t for k in ("journal", "audit", "activit"))
    wants_file = any(
        k in t
        for k in (
            "pdf",
            "télécharger",
            "telecharger",
            "telecharg",
            "download",
            "export",
            "fichier",
            "donne",
            "donner",
            "fournir",
            "envoie",
            "envoyer",
            "génér",
            "gener",
            "genere",
        )
    )
    if has_logs and wants_file:
        if any(k in t for k in ("excel", "xlsx", "xls", "csv", "tableur")):
            return "export_activity_logs_excel"
        return "export_activity_logs_pdf"
    return None


def parse_summary_intent(task: str) -> str:
    forced = detect_forced_admin_tool(task)
    if forced:
        return forced
    t = (task or "").lower()
    wants_download = any(
        k in t
        for k in (
            "pdf",
            "télécharger",
            "telecharger",
            "telecharg",
            "download",
            "export",
            "fichier",
            "génér",
            "gener",
            "genere",
            "donne",
            "donner",
            "fournir",
            "envoie",
            "envoyer",
        )
    )
    wants_logs = any(
        k in t
        for k in (
            "log",
            "journal",
            "audit",
            "activit",
            "événement",
            "evenement",
            "comportement",
        )
    )
    if wants_download and wants_logs:
        if any(k in t for k in ("excel", "xlsx", "xls", "csv", "tableur")):
            return "export_activity_logs_excel"
        return "export_activity_logs_pdf"
    if any(k in t for k in ("rapport", "résumé", "resume", "bilan", "jour", "24h", "aujourd", "comportement", "dangereux", "suspect")):
        return "daily_behavior_report"
    if wants_logs:
        return "analyze_logs"
    return "generate_summary"


def find_user_for_task(db: Session, task: str) -> User | None:
    task_l = (task or "").lower()
    id_match = re.search(
        r"(?:user|utilisateur|compte)\s*#?\s*(\d+)|\bid\s*#?\s*(\d+)",
        task_l,
    )
    if id_match:
        uid = id_match.group(1) or id_match.group(2)
        return db.get(User, int(uid))
    email_match = EMAIL_RE.search(task or "")
    if email_match:
        return db.scalar(select(User).where(User.email == email_match.group(0)))
    name_match = re.search(r"(?:compte|user|utilisateur)\s+[\"']?([a-z0-9._-]+)[\"']?", task_l)
    if name_match:
        token = name_match.group(1)
        if token.isdigit():
            return db.get(User, int(token))
        return db.scalar(
            select(User).where(or_(User.full_name.ilike(f"%{token}%"), User.email.ilike(f"%{token}%")))
        )
    words = [w for w in re.findall(r"[a-z0-9._-]+", task_l) if len(w) >= 3]
    skip = {
        "veux", "vouloir", "compte", "user", "utilisateur", "suspendre", "suspend",
        "reactiver", "réactiver", "fichier", "excel", "mail", "email", "colis", "tracking",
    }
    for word in reversed(words):
        if word in skip:
            continue
        found = db.scalar(
            select(User).where(or_(User.full_name.ilike(f"%{word}%"), User.email.ilike(f"%{word}%")))
        )
        if found:
            return found
    return None


def aggregate_user_behavior(db: Session, *, hours: int = 24, limit_users: int = 50) -> dict[str, Any]:
    """Agrégation déterministe pour rapports admin (faits, pas interprétation LLM)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs = list(
        db.scalars(
            select(ActivityLog).where(ActivityLog.created_at >= since).order_by(ActivityLog.created_at.desc())
        ).all()
    )
    by_user: dict[int, dict[str, Any]] = {}
    action_totals: dict[str, int] = {}

    for row in logs:
        action_totals[row.action] = action_totals.get(row.action, 0) + 1
        uid = row.user_id or row.actor_user_id
        if not uid:
            continue
        bucket = by_user.setdefault(
            uid,
            {
                "user_id": uid,
                "actions": {},
                "security_events": 0,
                "settings_changes": 0,
                "chat_events": 0,
                "exports": 0,
                "samples": [],
            },
        )
        bucket["actions"][row.action] = bucket["actions"].get(row.action, 0) + 1
        if row.category == "security" or row.level in ("WARNING", "CRITICAL"):
            bucket["security_events"] += 1
        if row.action.startswith("settings."):
            bucket["settings_changes"] += 1
        if row.action.startswith("chat."):
            bucket["chat_events"] += 1
        if "export" in row.action:
            bucket["exports"] += 1
        if len(bucket["samples"]) < 5:
            bucket["samples"].append(
                {
                    "action": row.action,
                    "message": (row.message or "")[:160],
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                    "level": row.level,
                }
            )

    chat_counts: dict[int, int] = {}
    chat_rows = db.execute(
        select(ChatSession.user_id, func.count())
        .select_from(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatMessage.sender == MessageSender.user.value, ChatMessage.created_at >= since)
        .group_by(ChatSession.user_id)
    ).all()
    for uid, cnt in chat_rows:
        if uid:
            chat_counts[int(uid)] = int(cnt)

    users_map: dict[int, User] = {}
    if by_user or chat_counts:
        ids = set(by_user.keys()) | set(chat_counts.keys())
        for u in db.scalars(select(User).where(User.id.in_(list(ids)))).all():
            users_map[u.id] = u

    flags: list[dict[str, Any]] = []
    for uid, data in by_user.items():
        user = users_map.get(uid)
        chat_n = chat_counts.get(uid, 0) + data["chat_events"]
        risk_score = 0
        reasons: list[str] = []
        if chat_n >= 30:
            risk_score += 2
            reasons.append(f"volume chat élevé ({chat_n} événements / {hours}h)")
        if data["settings_changes"] >= 5:
            risk_score += 2
            reasons.append(f"changements paramètres fréquents ({data['settings_changes']})")
        if data["security_events"] >= 2:
            risk_score += 3
            reasons.append(f"événements sécurité ({data['security_events']})")
        if risk_score >= 2:
            flags.append(
                {
                    "user_id": uid,
                    "email": user.email if user else "",
                    "full_name": user.full_name if user else "",
                    "risk_score": risk_score,
                    "reasons": reasons,
                    "chat_events": chat_n,
                    "settings_changes": data["settings_changes"],
                    "security_events": data["security_events"],
                    "action_samples": data["samples"],
                }
            )

    flags.sort(key=lambda x: x["risk_score"], reverse=True)
    return {
        "period_hours": hours,
        "logs_total": len(logs),
        "unique_users": len(by_user),
        "action_totals": action_totals,
        "risk_flags": flags[:limit_users],
        "open_tickets": int(
            db.scalar(
                select(func.count()).select_from(SupportTicket).where(
                    SupportTicket.status.in_((SupportTicketStatus.open, SupportTicketStatus.pending))
                )
            )
            or 0
        ),
        "open_security_incidents": int(
            db.scalar(
                select(func.count())
                .select_from(SecurityIncident)
                .where(SecurityIncident.status.in_(("open", "acknowledged")))
            )
            or 0
        ),
        "notifications_unread": int(
            db.scalar(
                select(func.count()).select_from(PlatformNotification).where(PlatformNotification.is_read.is_(False))
            )
            or 0
        ),
    }


def parse_support_intent(task: str) -> str:
    t = (task or "").lower()
    reply_kw = ("répond", "repond", "reply", "réponse", "reponse", "envoy", "envoi", "envoie", "message")
    ticket_kw = ("ticket", "support", "plainte", "demande")
    if any(k in t for k in reply_kw) and (any(k in t for k in ticket_kw) or TICKET_ID_RE.search(task or "")):
        return "reply_support_ticket"
    return "analyze_tickets"


def find_ticket_for_task(db: Session, task: str) -> SupportTicket | None:
    id_match = TICKET_ID_RE.search(task or "")
    if id_match:
        return db.get(SupportTicket, int(id_match.group(1)))
    tn_match = re.search(r"\b(TKT[-_]?\w+)\b", task or "", re.I)
    if tn_match:
        return db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == tn_match.group(1)))
    quoted = re.search(r"[\"']([^\"']{5,120})[\"']", task or "")
    if quoted:
        token = quoted.group(1).strip()
        return db.scalar(
            select(SupportTicket).where(
                or_(SupportTicket.subject.ilike(f"%{token}%"), SupportTicket.message.ilike(f"%{token}%"))
            ).order_by(SupportTicket.created_at.desc())
        )
    words = [w for w in re.findall(r"[\wÀ-ÿ'-]{4,}", task or "") if w.lower() not in {
        "répondre", "repondre", "ticket", "support", "client", "message", "envoyer", "envoi",
        "urgent", "plainte", "admin", "agent", "mission",
    }]
    for word in reversed(words[-3:]):
        found = db.scalar(
            select(SupportTicket).where(
                or_(SupportTicket.subject.ilike(f"%{word}%"), SupportTicket.message.ilike(f"%{word}%"))
            ).order_by(SupportTicket.created_at.desc())
        )
        if found:
            return found
    return None


def ticket_context_dict(ticket: SupportTicket) -> dict[str, Any]:
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "initial_message": (ticket.message or "")[:600],
        "messages": [
            {
                "author_role": m.author_role,
                "body": (m.body or "")[:400],
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in (ticket.messages or [])
        ],
    }


def post_admin_support_reply(
    db: Session,
    *,
    ticket_id: int,
    body: str,
    admin_id: int,
) -> tuple[bool, dict[str, Any]]:
    """Publie une réponse admin sur un ticket (même logique que la route HTTP)."""
    from sqlalchemy.orm import joinedload

    ticket = db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages))
        .where(SupportTicket.id == ticket_id)
    )
    if not ticket:
        return False, {"error": "ticket_not_found"}
    if ticket.status == SupportTicketStatus.closed:
        return False, {"error": "ticket_closed"}
    reply_body = (body or "").strip()
    if not reply_body:
        return False, {"error": "empty_reply"}

    row = SupportTicketMessage(
        ticket_id=ticket.id,
        author_role="admin",
        author_user_id=admin_id,
        body=reply_body,
    )
    db.add(row)
    ticket.admin_note = reply_body[:500]
    if ticket.status == SupportTicketStatus.open:
        ticket.status = SupportTicketStatus.pending
    create_user_notification(
        db,
        user_id=ticket.user_id,
        type="admin_reply",
        title="Réponse du support",
        message=reply_body[:500],
        sender_id=admin_id,
        sender_role="admin",
        priority=ticket.priority or "medium",
        related_ticket_id=ticket.id,
        link=f"/notifications?ticket={ticket.id}",
    )
    notify_employee_ticket_admin_reply(db, ticket=ticket, admin_id=admin_id, body=reply_body)
    write_log(
        db,
        action="support.admin_reply",
        message=f"Réponse admin (agent mission) sur ticket #{ticket.id}",
        category="admin",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=admin_id,
        metadata={"ticket_id": ticket.id, "source": "agent_mission"},
        commit=False,
    )
    db.flush()
    return True, {
        "ticket_id": ticket.id,
        "message_id": row.id,
        "status_after": ticket.status,
        "subject": ticket.subject,
    }


def resolve_tool_for_mission(mission: AgentMission, task: str) -> str:
    at = mission.agent_type
    if at == "users":
        return parse_users_intent(task)
    if at == "tracking":
        return parse_tracking_intent(task)
    if at in ("logs", "summary"):
        return parse_summary_intent(task)
    if at == "support":
        return parse_support_intent(task)
    if at == "notifications":
        return "analyze_notifications"
    return "analyze_only"
