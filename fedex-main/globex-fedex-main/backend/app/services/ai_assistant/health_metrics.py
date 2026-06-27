"""Métriques santé IA — requêtes, latence, erreurs, outils."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _HealthState:
    total_requests: int = 0
    success_requests: int = 0
    error_requests: int = 0
    total_latency_ms: float = 0.0
    provider_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tool_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tool_success: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tool_failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_error: str | None = None
    last_mode: str = "gemini"
    last_request_at: float | None = None
    started_at: float = field(default_factory=time.time)


_lock = threading.Lock()
_state = _HealthState()


def record_request(
    *,
    mode: str,
    success: bool,
    latency_ms: float,
    error: str | None = None,
) -> None:
    with _lock:
        _state.total_requests += 1
        if success:
            _state.success_requests += 1
        else:
            _state.error_requests += 1
            _state.last_error = error
        _state.total_latency_ms += latency_ms
        _state.provider_counts[mode] += 1
        _state.last_mode = mode
        _state.last_request_at = time.time()


def record_tool_call(tool_name: str, *, success: bool, latency_ms: float) -> None:
    with _lock:
        _state.tool_counts[tool_name] += 1
        if success:
            _state.tool_success[tool_name] += 1
        else:
            _state.tool_failures[tool_name] += 1


def get_health_snapshot() -> dict[str, Any]:
    with _lock:
        total = _state.total_requests or 1
        avg_latency = _state.total_latency_ms / max(_state.total_requests, 1)
        success_rate = _state.success_requests / total
        top_tools = sorted(
            _state.tool_counts.items(), key=lambda x: x[1], reverse=True,
        )[:15]
        return {
            "active_provider": _state.last_mode,
            "status": _provider_status(_state.last_mode),
            "uptime_seconds": int(time.time() - _state.started_at),
            "total_requests": _state.total_requests,
            "success_requests": _state.success_requests,
            "error_requests": _state.error_requests,
            "success_rate": round(success_rate, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "provider_usage": dict(_state.provider_counts),
            "tool_usage": dict(_state.tool_counts),
            "tool_success": dict(_state.tool_success),
            "tool_failures": dict(_state.tool_failures),
            "top_tools": [{"name": n, "count": c} for n, c in top_tools],
            "last_error": _state.last_error,
            "last_request_at": _state.last_request_at,
        }


def _provider_status(mode: str) -> str:
    if mode in {"gemini", "gemini_pro"}:
        return "green"
    if mode == "ollama":
        return "orange"
    return "red"
