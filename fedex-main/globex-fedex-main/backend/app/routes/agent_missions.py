"""Routes admin — Agent Missions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.agent_missions import (
    AgentApprovalActionResponse,
    AgentApprovalRead,
    AgentExecutionLogRead,
    AgentMissionCreate,
    AgentMissionDetailResponse,
    AgentMissionListResponse,
    AgentMissionRead,
    AgentMissionResults,
    AgentMissionWorkflowUpdate,
)
from app.services import agent_mission_service as svc

router = APIRouter(prefix="/admin/agent-missions", tags=["admin-agent-missions"])


@router.get("/task-catalog")
def get_mission_task_catalog(
    _: User = Depends(require_role("admin")),
) -> list[dict]:
    from app.services.mission_task_catalog import catalog_for_api

    return catalog_for_api()


@router.get("", response_model=AgentMissionListResponse)
def list_agent_missions(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionListResponse:
    return svc.list_missions(db)


@router.post("", response_model=AgentMissionRead, status_code=status.HTTP_201_CREATED)
def create_agent_mission(
    payload: AgentMissionCreate,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.create_mission(db, admin, payload)


@router.get("/{mission_id}", response_model=AgentMissionDetailResponse)
def get_agent_mission(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionDetailResponse:
    detail = svc.get_mission(db, mission_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    return detail


@router.patch("/{mission_id}/workflow", response_model=AgentMissionRead)
def update_agent_mission_workflow(
    mission_id: int,
    payload: AgentMissionWorkflowUpdate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.update_mission_workflow(db, mission_id, payload)


@router.post("/{mission_id}/generate-plan", response_model=AgentMissionRead)
def generate_mission_plan(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.generate_plan(db, mission_id)


@router.post("/{mission_id}/approve-plan", response_model=AgentMissionRead)
def approve_mission_plan(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.approve_plan(db, mission_id)


@router.post("/{mission_id}/run", response_model=AgentMissionRead)
def run_agent_mission(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.run_mission(db, mission_id)


@router.post("/{mission_id}/cancel", response_model=AgentMissionRead)
def cancel_agent_mission(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.cancel_mission(db, mission_id)


@router.post("/{mission_id}/pause", response_model=AgentMissionRead)
def pause_agent_mission(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.pause_mission(db, mission_id)


@router.post("/{mission_id}/resume", response_model=AgentMissionRead)
def resume_agent_mission(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionRead:
    return svc.resume_mission(db, mission_id)


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_mission(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    svc.delete_mission(db, mission_id)


@router.get("/{mission_id}/results", response_model=AgentMissionResults)
def get_agent_mission_results(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentMissionResults:
    detail = svc.get_mission(db, mission_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission introuvable")
    return detail.results


@router.get("/{mission_id}/logs", response_model=list[AgentExecutionLogRead])
def get_agent_mission_logs(
    mission_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[AgentExecutionLogRead]:
    return svc.get_mission_logs(db, mission_id)


approvals_router = APIRouter(prefix="/admin/agent-approvals", tags=["admin-agent-approvals"])


@approvals_router.post("/{approval_id}/approve", response_model=AgentApprovalActionResponse)
def approve_agent_action(
    approval_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentApprovalActionResponse:
    approval, mission = svc.approve_request(db, approval_id, admin)
    return AgentApprovalActionResponse(approval=AgentApprovalRead.model_validate(approval), mission=mission)


@approvals_router.post("/{approval_id}/reject", response_model=AgentApprovalActionResponse)
def reject_agent_action(
    approval_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AgentApprovalActionResponse:
    approval, mission = svc.reject_request(db, approval_id, admin)
    return AgentApprovalActionResponse(approval=AgentApprovalRead.model_validate(approval), mission=mission)
