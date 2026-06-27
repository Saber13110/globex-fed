"""Connexion par code QR personnel (token opaque hashé en base)."""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole, UserStatus

QR_PAYLOAD_PREFIX = "globex-login:"


def digest_qr_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()


def build_qr_payload(token: str) -> str:
    return f"{QR_PAYLOAD_PREFIX}{token}"


def parse_qr_payload(raw: str) -> str:
    value = raw.strip()
    if value.startswith(QR_PAYLOAD_PREFIX):
        return value[len(QR_PAYLOAD_PREFIX) :]
    return value


def _new_raw_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_qr_login_token(db: Session, user: User, *, regenerate: bool = False) -> str:
    """Crée ou régénère le token brut du QR (client / employé actifs uniquement)."""
    if user.role not in (UserRole.client.value, UserRole.employe.value):
        raise ValueError("role_not_allowed")
    if user.status != UserStatus.active.value:
        raise ValueError("account_not_active")

    if user.qr_login_token_digest and not regenerate:
        raise ValueError("token_not_retrievable")

    raw = _new_raw_token()
    user.qr_login_token_digest = digest_qr_token(raw)
    db.commit()
    db.refresh(user)
    return raw


def get_or_create_qr_login_token(db: Session, user: User) -> tuple[str | None, bool]:
    """Retourne (payload, created). Si un QR existe déjà, payload=None et created=False."""
    if user.role not in (UserRole.client.value, UserRole.employe.value):
        raise ValueError("role_not_allowed")
    if user.status != UserStatus.active.value:
        raise ValueError("account_not_active")

    if user.qr_login_token_digest:
        return None, False

    raw = _new_raw_token()
    user.qr_login_token_digest = digest_qr_token(raw)
    db.commit()
    db.refresh(user)
    return build_qr_payload(raw), True


def regenerate_qr_login_token(db: Session, user: User) -> str:
    raw = _new_raw_token()
    if user.role not in (UserRole.client.value, UserRole.employe.value):
        raise ValueError("role_not_allowed")
    if user.status != UserStatus.active.value:
        raise ValueError("account_not_active")
    user.qr_login_token_digest = digest_qr_token(raw)
    db.commit()
    db.refresh(user)
    return build_qr_payload(raw)


def find_user_by_qr_token(db: Session, raw_payload: str) -> User | None:
    token = parse_qr_payload(raw_payload)
    if not token:
        return None
    digest = digest_qr_token(token)
    return db.scalars(select(User).where(User.qr_login_token_digest == digest)).first()


def validate_user_for_qr_login(user: User) -> None:
    if user.role == UserRole.admin.value:
        raise ValueError("admin_not_allowed")
    if user.status == UserStatus.pending.value:
        raise ValueError("pending")
    if user.status == UserStatus.invited.value:
        raise ValueError("invited")
    if user.status == UserStatus.suspended.value:
        raise ValueError("suspended")
