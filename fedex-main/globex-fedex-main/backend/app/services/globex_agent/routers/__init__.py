"""Routeurs admin Globex Agent — pattern client."""

from app.services.globex_agent.routers.executor import plan_to_tool_calls
from app.services.globex_agent.routers.platform_router import plan_admin_platform_task

__all__ = ["plan_admin_platform_task", "plan_to_tool_calls"]
