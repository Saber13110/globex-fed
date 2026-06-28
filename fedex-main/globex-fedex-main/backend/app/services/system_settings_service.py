"""Persistance et fusion des paramètres système administrateur."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.system_settings import SystemSettings
from app.schemas.system_settings import (
    AiSettings,
    IntegrationSettings,
    NotificationSettings,
    SecuritySettings,
    SmtpIntegrationSettings,
    SystemSettingsPayload,
    SystemSettingsPatch,
    SystemSettingsRead,
)


def _defaults_from_env(settings: Settings) -> SystemSettingsPayload:
    return SystemSettingsPayload(
        notifications=NotificationSettings(),
        security=SecuritySettings(mfa_enabled=settings.two_factor_enabled),
        integrations=IntegrationSettings(
            smtp=SmtpIntegrationSettings(
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user,
                use_tls=settings.smtp_use_tls,
                password_set=bool(settings.smtp_password),
            )
        ),
        ai=AiSettings(
            provider=_map_provider(settings.llm_primary_provider),
            temperature=0.7,
            max_tokens=2048,
            system_prompt="",
        ),
    )


def _map_provider(raw: str) -> str:
    p = (raw or "gemini").lower()
    if p in ("gemini", "openai", "claude", "ollama"):
        return p
    return "gemini"


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def get_or_create_row(db: Session) -> SystemSettings:
    row = db.get(SystemSettings, 1)
    if row is None:
        defaults = _defaults_from_env(get_settings())
        row = SystemSettings(id=1, settings_json=defaults.model_dump_json())
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def load_settings(db: Session) -> SystemSettingsRead:
    row = get_or_create_row(db)
    env_defaults = _defaults_from_env(get_settings())
    try:
        stored = json.loads(row.settings_json or "{}")
    except json.JSONDecodeError:
        stored = {}
    merged = _deep_merge(env_defaults.model_dump(), stored)
    payload = SystemSettingsPayload.model_validate(merged)
    updated = row.updated_at
    if updated and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return SystemSettingsRead(**payload.model_dump(), updated_at=updated)


def patch_settings(db: Session, patch: SystemSettingsPatch) -> SystemSettingsRead:
    current = load_settings(db)
    data = current.model_dump(exclude={"updated_at"})
    patch_data = patch.model_dump(exclude_unset=True)
    merged = _deep_merge(data, patch_data)
    row = get_or_create_row(db)
    row.settings_json = json.dumps(merged, ensure_ascii=False)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return load_settings(db)


def get_mfa_enabled(db: Session) -> bool:
    return load_settings(db).security.mfa_enabled


def get_ai_settings(db: Session) -> AiSettings:
    return load_settings(db).ai


def get_smtp_overrides(db: Session) -> dict[str, Any]:
    smtp = load_settings(db).integrations.smtp
    return smtp.model_dump()
