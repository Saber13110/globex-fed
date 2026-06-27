"""Utilitaires timeout — garantit qu'aucune étape ne bloque indéfiniment."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Deadline:
    """Horloge partagée pour le pipeline agent."""

    def __init__(self, seconds: float) -> None:
        self.deadline = time.monotonic() + max(seconds, 1.0)

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())


def run_with_timeout(
    fn: Callable[[], T],
    *,
    timeout_seconds: float,
    label: str = "operation",
    default: T | None = None,
) -> T | None:
    """Exécute fn dans un thread avec timeout (pour appels LLM bloquants)."""
    if timeout_seconds <= 0:
        return default
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-timeout") as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            logger.warning("[AI] timeout — %s (%.1fs)", label, timeout_seconds)
            return default
        except Exception as exc:
            logger.warning("[AI] error — %s: %s", label, exc)
            return default
