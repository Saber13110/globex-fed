"""Routes admin — IDS sécurité."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.security import (
    SecurityAgentRequest,
    SecurityAgentResponse,
    SecurityIncidentListResponse,
    SecurityIncidentRead,
    SecurityIncidentResolveRequest,
    SecurityPolicyRead,
    SecurityPolicyRule,
    SecurityPolicyUpdateRequest,
)
from app.services.activity_log_service import client_ip
from app.services.security_agent_service import process_security_agent_message
from app.services.security_ids_service import (
    get_or_create_policy,
    incident_to_read,
    list_incidents,
    load_policy_rules,
    reactivate_user,
    resolve_incident,
    run_ai_ids_scan,
    run_rule_scan,
    suspend_user,
)

router = APIRouter(prefix="/admin/security", tags=["admin-security"])


def _policy_read(db: Session) -> SecurityPolicyRead:
    policy = get_or_create_policy(db)
    return SecurityPolicyRead(
        auto_mode_enabled=policy.auto_mode_enabled,
        ai_ids_enabled=policy.ai_ids_enabled,
        rules=[SecurityPolicyRule(**r) for r in load_policy_rules(policy)],
        enabled_by_admin_id=policy.enabled_by_admin_id,
        enabled_at=policy.enabled_at,
        updated_at=policy.updated_at,
    )


@router.get("/incidents", response_model=SecurityIncidentListResponse)
def get_security_incidents(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    status: str = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SecurityIncidentListResponse:
    rows, total, open_count = list_incidents(db, status=status, limit=limit, offset=offset)
    return SecurityIncidentListResponse(
        items=[SecurityIncidentRead(**incident_to_read(db, r)) for r in rows],
        total=total,
        open_count=open_count,
    )


@router.patch("/incidents/{incident_id}", response_model=SecurityIncidentRead)
def patch_security_incident(
    incident_id: int,
    payload: SecurityIncidentResolveRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SecurityIncidentRead:
    row = resolve_incident(
        db,
        incident_id,
        status=payload.status,
        admin_id=admin.id,
        note=payload.note or "",
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident introuvable.")
    return SecurityIncidentRead(**incident_to_read(db, row))


@router.post("/incidents/{incident_id}/suspend-user", response_model=dict)
def suspend_user_from_incident(
    incident_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    from app.models.security_incident import SecurityIncident

    inc = db.get(SecurityIncident, incident_id)
    if inc is None or not inc.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident ou utilisateur introuvable.")
    ok = suspend_user(
        db,
        inc.user_id,
        reason=f"Suspension manuelle — incident #{incident_id}",
        actor_admin_id=admin.id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Suspension impossible.")
    resolve_incident(db, incident_id, status="resolved", admin_id=admin.id, note="Compte suspendu par admin")
    return {"suspended": True, "user_id": inc.user_id}


@router.get("/policy", response_model=SecurityPolicyRead)
def get_security_policy(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SecurityPolicyRead:
    return _policy_read(db)


@router.patch("/policy", response_model=SecurityPolicyRead)
def update_security_policy(
    payload: SecurityPolicyUpdateRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SecurityPolicyRead:
    import json
    from datetime import datetime, timezone

    policy = get_or_create_policy(db)
    if payload.auto_mode_enabled is not None:
        policy.auto_mode_enabled = payload.auto_mode_enabled
        if payload.auto_mode_enabled:
            policy.enabled_by_admin_id = admin.id
            policy.enabled_at = datetime.now(timezone.utc)
    if payload.ai_ids_enabled is not None:
        policy.ai_ids_enabled = payload.ai_ids_enabled
    if payload.rules is not None:
        policy.rules_json = json.dumps([r.model_dump() for r in payload.rules], ensure_ascii=False)
    db.commit()
    return _policy_read(db)


@router.post("/scan", response_model=dict)
def trigger_ids_scan(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    include_ai: bool = Query(default=True),
) -> dict:
    rules = run_rule_scan(db)
    ai = run_ai_ids_scan(db) if include_ai else 0
    return {"rules_incidents": rules, "ai_incidents": ai}


@router.post("/agent", response_model=SecurityAgentResponse)
def security_agent(
    payload: SecurityAgentRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SecurityAgentResponse:
    result = process_security_agent_message(
        db,
        admin=admin,
        message=payload.message,
        ip_address=client_ip(request),
    )
    return SecurityAgentResponse(**result)


@router.post("/users/{user_id}/reactivate", response_model=dict)
def reactivate_suspended_user(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if not reactivate_user(db, user_id, actor_admin_id=admin.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    return {"reactivated": True, "user_id": user_id}
