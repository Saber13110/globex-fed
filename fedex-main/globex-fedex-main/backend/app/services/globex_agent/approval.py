"""Création d'approbations pour actions sensibles Globex Agent."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_approval_request import AgentApprovalRequest
from app.models.agent_mission import AgentMission
from app.models.agent_mission_step import AgentMissionStep
from app.models.user import User


def create_tool_approval(
    db: Session,
    admin: User,
    *,
    tool_name: str,
    args: dict[str, Any],
    hint: str | None = None,
) -> tuple[int, int]:
    """Crée mission + étape + demande d'approbation. Retourne (approval_id, mission_id)."""
    mission = AgentMission(
        admin_id=admin.id,
        agent_type="globex-agent",
        task_description=f"Globex OS — {tool_name}",
        status="waiting_permission",
        schedule_type="now",
        plan_json=json.dumps({"source": "globex-agent", "tool": tool_name}, ensure_ascii=False),
        require_approval_sensitive=True,
        notify_on_start=False,
        notify_on_complete=False,
    )
    db.add(mission)
    db.flush()

    step = AgentMissionStep(
        mission_id=mission.id,
        step_order=1,
        title=f"Action : {tool_name}",
        description=hint or f"Exécution de {tool_name}",
        action_type=tool_name,
        is_sensitive=True,
        status="waiting_approval",
    )
    db.add(step)
    db.flush()

    payload = {"tool": tool_name, "args": args, "action_type": tool_name, "source": "globex-agent"}
    approval = AgentApprovalRequest(
        mission_id=mission.id,
        step_id=step.id,
        action_type=tool_name,
        description=hint or f"Autoriser : {tool_name}",
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        status="pending",
    )
    db.add(approval)
    db.flush()
    return approval.id, mission.id
