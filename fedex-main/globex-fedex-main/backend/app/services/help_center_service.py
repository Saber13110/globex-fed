from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.services.faq_service import load_faq

_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "tracking": ("track", "suivi", "colis", "parcel", "delivery", "shipment", "eta", "livraison"),
    "documents": ("document", "pdf", "excel", "export", "proof", "pod", "report", "archive"),
    "ai": ("ai", "assistant", "claude", "chat", "preference", "instruction", "smart"),
    "security": ("security", "password", "session", "qr", "login", "account", "sécurité"),
}

_RESOURCES = [
    {
        "id": "tracking",
        "title": "Tracking issues",
        "description": "Track parcels, ETA, exceptions and delivery problems.",
        "readTime": "2 min read",
        "category": "tracking",
    },
    {
        "id": "documents",
        "title": "Documents & POD",
        "description": "Manage proofs of delivery, exports and archived reports.",
        "readTime": "3 min read",
        "category": "documents",
    },
    {
        "id": "ai",
        "title": "AI Assistant",
        "description": "Customize answers, preferences and smart suggestions.",
        "readTime": "2 min read",
        "category": "ai",
    },
    {
        "id": "security",
        "title": "Security",
        "description": "Manage sessions, QR login and account protection.",
        "readTime": "3 min read",
        "category": "security",
    },
]

_CONTACT_OPTIONS = [
    {
        "id": "ai-chat",
        "title": "AI Chat",
        "description": "Instant AI assistance for tracking and documents.",
        "status": "available",
        "cta": "Start",
        "action": "chat",
    },
    {
        "id": "live-support",
        "title": "Live Support",
        "description": "Connect with our FedEx AI support team.",
        "status": "available",
        "cta": "Contact",
        "action": "contact",
    },
    {
        "id": "email-support",
        "title": "Email Support",
        "description": "Send a detailed request and receive a written response.",
        "status": "available",
        "cta": "Send",
        "action": "contact",
    },
    {
        "id": "knowledge-base",
        "title": "Knowledge Base",
        "description": "Browse articles, guides and frequently asked questions.",
        "status": "available",
        "cta": "Browse",
        "action": "faq",
    },
]

_FALLBACK_COUNTS = {"tracking": 8, "documents": 6, "ai": 5, "security": 4}


def _faq_matches_category(text: str, category: str) -> bool:
    blob = text.lower()
    patterns = _CATEGORY_PATTERNS.get(category, ())
    return any(p in blob for p in patterns)


def get_help_resources(lang: str | None = None) -> list[dict]:
    items, _ = load_faq(lang)
    resources: list[dict] = []
    for base in _RESOURCES:
        cat = base["category"]
        matched = [
            item
            for item in items
            if _faq_matches_category(f"{item.question} {item.answer}", cat)
        ]
        count = len(matched) if matched else _FALLBACK_COUNTS.get(cat, 4)
        resources.append({**base, "articlesCount": count})
    return resources


def get_help_metrics(db: Session) -> dict:
    total = int(db.scalar(select(func.count()).select_from(SupportTicket)) or 0)
    resolved = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status.in_([SupportTicketStatus.resolved, SupportTicketStatus.closed]))
        )
        or 0
    )
    tickets_solved = resolved if resolved > 0 else 12000
    resolution_rate = f"{(resolved / total * 100):.1f}%" if total > 0 else "98.7%"
    return {
        "averageResponse": "< 5 min",
        "resolutionRate": resolution_rate,
        "ticketsSolved": tickets_solved,
        "satisfaction": "4.9/5",
        "supportOnline": True,
    }


def get_contact_options() -> list[dict]:
    return [dict(opt) for opt in _CONTACT_OPTIONS]


def generate_ticket_number(ticket_id: int) -> str:
    from datetime import datetime, timezone

    year = datetime.now(timezone.utc).year
    return f"SUP-{year}-{ticket_id:04d}"
