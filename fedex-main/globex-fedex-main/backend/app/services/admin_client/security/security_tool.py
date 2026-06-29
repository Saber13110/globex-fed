"""Outils Security IDS admin — délégation service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.admin_client.security import security_service
from app.services.admin_client.security.security_types import SecurityPlan


def list_incidents(db: Session, plan: SecurityPlan) -> dict:
    items, total, open_count = security_service.list_incidents_filtered(
        db,
        status_filter=plan.status_filter,
        severity_filter=plan.severity_filter,
        limit=plan.limit,
    )
    return {
        "incidents": items,
        "total": total,
        "open_count": open_count,
    }


def get_incident_detail(db: Session, incident_id: int) -> dict:
    return security_service.get_incident_detail(db, incident_id)


def run_scan(db: Session, plan: SecurityPlan) -> dict:
    return security_service.run_ids_scan(db, include_ai=plan.include_ai_scan)


def build_summary(db: Session, plan: SecurityPlan) -> dict:
    return security_service.summarize_open_incidents(db, limit=plan.limit)


def build_report(db: Session, plan: SecurityPlan) -> dict:
    return security_service.build_security_report(db)
