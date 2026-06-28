from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.system_settings import SystemHealthResponse, SystemOperationResponse
from app.services.activity_log_service import client_ip, write_log
from app.services.system_health_service import build_health
from app.services.system_ops_service import clear_cache, manual_backup, reindex_data

router = APIRouter(tags=["system"])


@router.get("/health", response_model=SystemHealthResponse)
def system_health(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemHealthResponse:
    return build_health(db)


@router.post("/cache/clear", response_model=SystemOperationResponse)
def system_clear_cache(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemOperationResponse:
    result = clear_cache()
    write_log(
        db,
        action="system.cache_clear",
        message="Cache système vidé",
        category="system",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return result


@router.post("/reindex", response_model=SystemOperationResponse)
def system_reindex(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemOperationResponse:
    result = reindex_data(db)
    write_log(
        db,
        action="system.reindex",
        message="Réindexation des données",
        category="system",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return result


@router.post("/backup", response_model=SystemOperationResponse)
def system_backup(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemOperationResponse:
    result = manual_backup(db)
    write_log(
        db,
        action="system.backup",
        message="Sauvegarde manuelle créée",
        category="system",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata=result.detail or {},
        commit=True,
    )
    return result
