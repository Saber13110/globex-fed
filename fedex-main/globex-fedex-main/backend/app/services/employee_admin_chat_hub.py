"""Hub WebSocket pour la communication employé ↔ administrateur."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket


@dataclass
class TypingState:
    sender_role: str
    sender_name: str
    expires_at: datetime


class EmployeeAdminChatHub:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._typing: dict[int, TypingState | None] = {}
        self._lock = asyncio.Lock()

    async def connect(self, employee_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(employee_id, set()).add(websocket)

    async def disconnect(self, employee_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(employee_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(employee_id, None)

    async def broadcast(self, employee_id: int, event: dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._connections.get(employee_id, set()))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                bucket = self._connections.get(employee_id)
                if bucket:
                    for ws in dead:
                        bucket.discard(ws)

    async def set_typing(
        self,
        employee_id: int,
        *,
        sender_role: str,
        sender_name: str,
        active: bool,
        ttl_seconds: int = 4,
    ) -> None:
        if active:
            self._typing[employee_id] = TypingState(
                sender_role=sender_role,
                sender_name=sender_name,
                expires_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=ttl_seconds),
            )
        else:
            self._typing.pop(employee_id, None)
        await self.broadcast(
            employee_id,
            {
                "type": "typing",
                "payload": {
                    "sender_role": sender_role,
                    "sender_name": sender_name,
                    "active": active,
                },
            },
        )

    def get_typing(self, employee_id: int) -> TypingState | None:
        state = self._typing.get(employee_id)
        if state is None:
            return None
        if state.expires_at < datetime.now(timezone.utc):
            self._typing.pop(employee_id, None)
            return None
        return state

    async def notify_message(self, employee_id: int, message: dict[str, Any], unread_count: int) -> None:
        await self.broadcast(employee_id, {"type": "message", "payload": message})
        await self.broadcast(employee_id, {"type": "unread", "payload": {"count": unread_count}})


employee_admin_chat_hub = EmployeeAdminChatHub()
