"""Vérifications de santé des services infrastructure."""

from __future__ import annotations

import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.system_settings import ServiceHealthItem, SystemHealthResponse, SystemInfoResponse
from app.services.email_service import is_email_configured
from app.services.system_settings_service import get_smtp_overrides


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _item(
    key: str,
    label: str,
    status: str,
    availability: float,
    latency_ms: float | None,
    detail: str = "",
) -> ServiceHealthItem:
    return ServiceHealthItem(
        key=key,
        label=label,
        status=status,  # type: ignore[arg-type]
        availability_percent=availability,
        latency_ms=latency_ms,
        last_check=_now(),
        detail=detail,
    )


def check_database(db: Session) -> ServiceHealthItem:
    start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return _item("database", "PostgreSQL", "online", 99.9, round(latency, 2), "Connexion active")
    except Exception as exc:  # noqa: BLE001
        return _item("database", "PostgreSQL", "offline", 0.0, None, str(exc))


def check_smtp(db: Session) -> ServiceHealthItem:
    settings = get_settings()
    overrides = get_smtp_overrides(db)
    host = overrides.get("host") or settings.smtp_host
    port = int(overrides.get("port") or settings.smtp_port)
    configured = is_email_configured() or bool(host and overrides.get("user"))
    if not configured:
        return _item("smtp", "SMTP", "disabled", 0.0, None, "SMTP non configuré")
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=3):
            latency = (time.perf_counter() - start) * 1000
        return _item("smtp", "SMTP", "online", 99.9, round(latency, 2), f"{host}:{port}")
    except Exception as exc:  # noqa: BLE001
        return _item("smtp", "SMTP", "degraded", 50.0, None, str(exc))


def check_fedex() -> ServiceHealthItem:
    settings = get_settings()
    if not settings.fedex_enabled:
        return _item("fedex", "FedEx API", "disabled", 0.0, None, "FedEx désactivé dans la configuration")
    if not settings.fedex_client_id or not settings.fedex_client_secret:
        return _item("fedex", "FedEx API", "offline", 0.0, None, "Identifiants FedEx manquants")
    start = time.perf_counter()
    try:
        url = f"{settings.fedex_base_url.rstrip('/')}/oauth/token"
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(
                url,
                data={"grant_type": "client_credentials"},
                auth=(settings.fedex_client_id, settings.fedex_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        latency = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return _item("fedex", "FedEx API", "online", 99.9, round(latency, 2), "Authentification OK")
        return _item("fedex", "FedEx API", "degraded", 70.0, round(latency, 2), f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return _item("fedex", "FedEx API", "offline", 0.0, None, str(exc))


def check_ai() -> ServiceHealthItem:
    settings = get_settings()
    if not settings.llm_enabled:
        return _item("ai", "IA / LLM", "disabled", 0.0, None, "LLM désactivé")
    provider = (settings.llm_primary_provider or "gemini").lower()
    start = time.perf_counter()
    try:
        if provider == "gemini":
            if not settings.gemini_api_key:
                return _item("ai", "IA / LLM", "offline", 0.0, None, "Clé Gemini manquante")
            return _item("ai", "IA (Gemini)", "online", 99.9, round((time.perf_counter() - start) * 1000, 2), settings.gemini_model)
        base = settings.ollama_base_url.rstrip("/")
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/api/tags")
        latency = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return _item("ai", "IA (Ollama)", "online", 99.9, round(latency, 2), settings.ollama_model)
        return _item("ai", "IA / LLM", "degraded", 60.0, round(latency, 2), f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return _item("ai", "IA / LLM", "offline", 0.0, None, str(exc))


def check_redis() -> ServiceHealthItem:
    return _item(
        "redis",
        "Redis",
        "not_configured",
        0.0,
        None,
        "Redis non déployé dans cet environnement",
    )


def check_storage() -> ServiceHealthItem:
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    start = time.perf_counter()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".health"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        latency = (time.perf_counter() - start) * 1000
        return _item("storage", "File Storage", "online", 99.9, round(latency, 2), str(data_dir))
    except Exception as exc:  # noqa: BLE001
        return _item("storage", "File Storage", "offline", 0.0, None, str(exc))


def build_health(db: Session) -> SystemHealthResponse:
    services = [
        check_smtp(db),
        check_fedex(),
        check_ai(),
        check_database(db),
        check_redis(),
        check_storage(),
    ]
    return SystemHealthResponse(services=services)


def build_system_info(db: Session) -> SystemInfoResponse:
    import os

    settings = get_settings()
    db.execute(text("SELECT 1"))
    db_ok = True
    updated = None
    try:
        from app.services.system_settings_service import get_or_create_row

        r = get_or_create_row(db)
        updated = r.updated_at
        if updated and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        updated = _now()

    return SystemInfoResponse(
        version=getattr(settings, "app_version", "2.4.0"),
        environment=os.getenv("ENVIRONMENT", "production"),
        database_status="Connectée" if db_ok else "Déconnectée",
        server=socket.gethostname(),
        last_updated=updated or _now(),
    )
