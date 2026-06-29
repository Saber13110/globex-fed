"""Outils agent utilisateurs admin — délégation users_service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.admin_client.users import users_service
from app.services.admin_client.users.users_types import UsersPlan, UsersToolError


def list_users(db: Session, plan: UsersPlan) -> list[dict[str, Any]]:
    if plan.list_variant == "ever_suspended":
        items = users_service.list_users_ever_suspended(
            db,
            role=plan.role_filter,
            q=plan.search_query,
            limit=plan.limit,
        )
    else:
        items = users_service.list_users_filtered(
            db,
            role=plan.role_filter,
            status=plan.status_filter,
            q=plan.search_query,
            limit=plan.limit,
            sort_by=plan.sort_by or (
                "last_activity" if plan.list_variant == "activity" else None
            ),
        )
    return [item.model_dump() for item in items]


def get_user_detail(db: Session, user_id: int) -> dict[str, Any]:
    return users_service.get_user_detail(db, user_id).model_dump()


def get_user_logs(db: Session, user_id: int, *, limit: int = 25) -> dict[str, Any]:
    return users_service.get_user_logs(db, user_id, limit=limit).model_dump()


def get_user_permissions(db: Session, user_id: int) -> dict[str, Any]:
    return users_service.get_user_permissions(db, user_id)
