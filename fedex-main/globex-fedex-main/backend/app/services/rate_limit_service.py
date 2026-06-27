"""Limitation de débit en mémoire (par clé IP / email) pour les endpoints sensibles."""

from __future__ import annotations

import threading
import time

from fastapi import HTTPException, status

_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}


def check_rate_limit(key: str, *, max_attempts: int, window_seconds: int) -> None:
    """Lève HTTP 429 si la clé a dépassé le quota dans la fenêtre glissante."""
    if max_attempts <= 0:
        return
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        hits = [t for t in _attempts.get(key, []) if t > cutoff]
        if len(hits) >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de tentatives. Réessayez dans quelques minutes.",
            )
        hits.append(now)
        _attempts[key] = hits


def record_attempt(key: str, *, window_seconds: int) -> None:
    """Enregistre une tentative (échec) sans vérifier le plafond."""
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        hits = [t for t in _attempts.get(key, []) if t > cutoff]
        hits.append(now)
        _attempts[key] = hits


def clear_keys(*keys: str) -> None:
    """Réinitialise les compteurs après une connexion réussie."""
    with _lock:
        for key in keys:
            _attempts.pop(key, None)


def clear_all_rate_limits() -> int:
    """Vide tous les compteurs (outil admin)."""
    with _lock:
        count = len(_attempts)
        _attempts.clear()
        return count
