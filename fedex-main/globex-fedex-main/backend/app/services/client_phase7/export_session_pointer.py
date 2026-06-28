"""Pointeur dernier export par session — cache mémoire TTL 30 min."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

_TTL_SECONDS = 1800
_pointers: dict[int, tuple[float, dict[str, Any]]] = {}


@dataclass
class SessionExportPointer:
    export_token: str
    fmt: str
    filename: str


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (exp, _) in _pointers.items() if exp <= now]
    for k in expired:
        _pointers.pop(k, None)


def remember_session_export(
    session_id: int,
    *,
    export_token: str | None,
    fmt: str,
    filename: str,
) -> None:
    if not export_token:
        return
    _purge_expired()
    _pointers[int(session_id)] = (
        time.time() + _TTL_SECONDS,
        {
            "export_token": export_token,
            "fmt": fmt,
            "filename": filename,
        },
    )


def get_session_export_pointer(session_id: int) -> SessionExportPointer | None:
    _purge_expired()
    entry = _pointers.get(int(session_id))
    if not entry:
        return None
    expires, payload = entry
    if expires <= time.time():
        _pointers.pop(int(session_id), None)
        return None
    token = str(payload.get("export_token") or "").strip()
    if not token:
        return None
    return SessionExportPointer(
        export_token=token,
        fmt=str(payload.get("fmt") or "pdf"),
        filename=str(payload.get("filename") or "export.pdf"),
    )


def clear_all_session_export_pointers() -> None:
    """Vide le cache (tests / isolation)."""
    _pointers.clear()
