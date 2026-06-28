"""API Workspace Jarvis — agrégation Globex FedEx pour /dashboard."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jarvis.interfaces.api.globex import GlobexApprovalResponse, _get_token
from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api/workspace/globex", tags=["workspace-globex"])


class WorkspaceApproveBody(BaseModel):
    approval_id: int


async def _fedex_get(path: str) -> Any:
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")
    token = await _get_token()
    base = settings.globex_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
    return resp.json()


async def _fedex_post(path: str) -> dict[str, Any]:
    if not settings.globex_os_enabled:
        raise HTTPException(status_code=503, detail="Globex OS désactivé.")
    token = await _get_token()
    base = settings.globex_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
    return resp.json() if resp.content else {}


@router.get("/overview")
async def workspace_globex_overview() -> dict[str, Any]:
    return await _fedex_get("/api/globex-agent/workspace/overview")


@router.get("/initiatives")
async def workspace_globex_initiatives() -> list[dict[str, Any]]:
    data = await _fedex_get("/api/globex-agent/workspace/initiatives")
    return data if isinstance(data, list) else []


@router.get("/missions")
async def workspace_globex_missions() -> list[dict[str, Any]]:
    data = await _fedex_get("/api/globex-agent/workspace/missions")
    return data if isinstance(data, list) else []


@router.get("/analytics")
async def workspace_globex_analytics() -> dict[str, Any]:
    return await _fedex_get("/api/globex-agent/workspace/analytics")


@router.get("/catalog")
async def workspace_globex_catalog() -> dict[str, Any]:
    return await _fedex_get("/api/globex-agent/tools/catalog")


@router.get("/health")
async def workspace_globex_health() -> dict[str, Any]:
    return await _fedex_get("/api/globex-agent/health")


@router.get("/proactive/status")
async def workspace_globex_proactive_status() -> dict[str, Any]:
    return await _fedex_get("/api/globex-agent/proactive/status")


@router.post("/approve/{approval_id}", response_model=GlobexApprovalResponse)
async def workspace_globex_approve(approval_id: int) -> GlobexApprovalResponse:
    data = await _fedex_post(f"/api/globex-agent/approve/{approval_id}")
    return GlobexApprovalResponse(
        approval_id=int(data.get("approval_id") or approval_id),
        status=str(data.get("status") or "approved"),
        reply=data.get("reply"),
        mission_id=data.get("mission_id"),
    )


@router.post("/reject/{approval_id}", response_model=GlobexApprovalResponse)
async def workspace_globex_reject(approval_id: int) -> GlobexApprovalResponse:
    data = await _fedex_post(f"/api/globex-agent/reject/{approval_id}")
    return GlobexApprovalResponse(
        approval_id=int(data.get("approval_id") or approval_id),
        status=str(data.get("status") or "rejected"),
        reply=data.get("reply"),
        mission_id=data.get("mission_id"),
    )


@router.get("/enabled")
async def workspace_globex_enabled() -> dict[str, bool]:
    return {"enabled": bool(settings.globex_os_enabled)}
