"""Profilage des étapes RAG / GPT — timings et logs structurés."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class StepTiming:
    name: str
    elapsed_ms: int
    detail: str | None = None


@dataclass
class RagProfile:
    label: str
    steps: list[StepTiming] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def add(self, name: str, *, detail: str | None = None, since: float | None = None) -> None:
        now = time.perf_counter()
        start = since if since is not None else self._t0
        elapsed_ms = int((now - start) * 1000)
        self.steps.append(StepTiming(name=name, elapsed_ms=elapsed_ms, detail=detail))
        self._t0 = now
        msg = f"[RAG/{self.label}] {name}={elapsed_ms}ms"
        if detail:
            msg += f" ({detail})"
        logger.info(msg)

    def total_ms(self) -> int:
        return sum(s.elapsed_ms for s in self.steps)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total_ms": self.total_ms(),
            "steps": [
                {"name": s.name, "elapsed_ms": s.elapsed_ms, "detail": s.detail}
                for s in self.steps
            ],
        }


@contextmanager
def timed_step(profile: RagProfile | None, name: str, *, detail: str | None = None) -> Iterator[None]:
    if profile is None:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        profile.add(name, detail=detail, since=t0)
