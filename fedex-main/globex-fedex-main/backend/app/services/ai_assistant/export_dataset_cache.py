"""Cache temporaire des datasets export — garantit le même contenu au téléchargement."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_TTL_SECONDS = 1800  # 30 min
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (exp, _) in _cache.items() if exp <= now]
    for k in expired:
        _cache.pop(k, None)


def store_export_dataset(
    *,
    admin_id: int,
    module: str,
    items: list[dict[str, Any]],
    limit: int,
    source: str,
    filename: str,
    fmt: str = "pdf",
    meta: dict[str, Any] | None = None,
) -> str:
    """Stocke le dataset normalisé — retourne un token pour le téléchargement."""
    _purge_expired()
    token = uuid.uuid4().hex
    _cache[token] = (
        time.time() + _TTL_SECONDS,
        {
            "admin_id": admin_id,
            "module": module,
            "items": items,
            "limit": limit,
            "source": source,
            "filename": filename,
            "format": fmt,
            "meta": meta or {},
        },
    )
    logger.info("[EXPORT] cache_stored token=%s module=%s count=%s source=%s", token[:8], module, len(items), source)
    return token


def store_pdf_blob(
    *,
    admin_id: int,
    pdf_bytes: bytes,
    filename: str,
    module: str = "text",
    meta: dict[str, Any] | None = None,
) -> str:
    """Stocke un PDF déjà généré (texte libre) pour téléchargement via export_token."""
    _purge_expired()
    token = uuid.uuid4().hex
    _cache[token] = (
        time.time() + _TTL_SECONDS,
        {
            "admin_id": admin_id,
            "module": module,
            "items": [],
            "limit": 0,
            "source": "text_pdf",
            "filename": filename,
            "format": "pdf",
            "pdf_bytes": pdf_bytes,
            "meta": meta or {},
        },
    )
    logger.info("[EXPORT] pdf_blob_stored token=%s module=%s bytes=%s", token[:8], module, len(pdf_bytes))
    return token


def _owner_matches(payload: dict[str, Any], owner_id: int) -> bool:
    """Vérifie propriétaire — admin_id (legacy) ou owner_id (client)."""
    if payload.get("owner_id") is not None:
        return payload.get("owner_id") == owner_id
    return payload.get("admin_id") == owner_id


def store_client_pdf_blob(
    *,
    user_id: int,
    pdf_bytes: bytes,
    filename: str,
    module: str = "text",
    meta: dict[str, Any] | None = None,
) -> str:
    """Stocke un PDF client (texte libre / résumé) pour téléchargement via export_token."""
    _purge_expired()
    token = uuid.uuid4().hex
    _cache[token] = (
        time.time() + _TTL_SECONDS,
        {
            "owner_id": user_id,
            "module": module,
            "items": [],
            "limit": 0,
            "source": "client_text_pdf",
            "filename": filename,
            "format": "pdf",
            "pdf_bytes": pdf_bytes,
            "meta": meta or {},
        },
    )
    logger.info(
        "[EXPORT] client_pdf_blob_stored token=%s module=%s bytes=%s",
        token[:8],
        module,
        len(pdf_bytes),
    )
    return token


def get_export_dataset(token: str, *, admin_id: int) -> dict[str, Any] | None:
    """Récupère un dataset cache — vérifie l'admin."""
    return get_owner_export_dataset(token, owner_id=admin_id)


def get_owner_export_dataset(token: str, *, owner_id: int) -> dict[str, Any] | None:
    """Récupère un dataset cache — vérifie le propriétaire (admin ou client)."""
    _purge_expired()
    entry = _cache.get(token)
    if not entry:
        logger.warning("[EXPORT] cache_miss token=%s", token[:8] if token else "?")
        return None
    expires, payload = entry
    if expires <= time.time():
        _cache.pop(token, None)
        return None
    if not _owner_matches(payload, owner_id):
        logger.warning("[EXPORT] cache_owner_mismatch token=%s", token[:8])
        return None
    return payload


def pop_export_dataset(token: str, *, admin_id: int) -> dict[str, Any] | None:
    """Récupère et supprime (usage unique optionnel — on garde pour re-téléchargement)."""
    return get_export_dataset(token, admin_id=admin_id)
