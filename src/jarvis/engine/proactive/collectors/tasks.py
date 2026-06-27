"""
TaskCollector — récupère les tâches Notion non cochées.
Réutilise le tool notion existant.
"""

from __future__ import annotations

from datetime import datetime

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.contracts import NotionReadTool


class TaskCollector(CollectorBase):
    name = "tasks"

    def __init__(self, notion_tool: NotionReadTool) -> None:
        self._notion_tool = notion_tool

    async def _collect(self) -> list[ContextItem]:
        result = await self._notion_tool.execute()

        if result.is_error or not result.content:
            return []

        items = []
        now = datetime.now()

        for line in result.content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            items.append(
                ContextItem(
                    type=ItemType.TASK,
                    title=line,
                    summary=line,
                    raw=line,
                    source="notion",
                    timestamp=now,
                    priority=Priority.MEDIUM,
                )
            )

        return items
