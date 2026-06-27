"""Double authentification par code OTP envoyé par email."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash, verify_password
from app.models.login_otp_challenge import LoginOtpChallenge
from app.models.user import User
from app.services.email_service import is_email_configured, send_email

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def is_two_factor_active(db: Session | None = None) -> bool:
    if not is_email_configured():
        return False
    if db is not None:
        try:
            from app.services.system_settings_service import get_mfa_enabled

            return get_mfa_enabled(db)
        except Exception:  # noqa: BLE001
            pass
    settings = get_settings()
    return settings.two_factor_enabled


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked = local[0] + "***"
    else:
        masked = local[0] + "***" + local[-1]
    return f"{masked}@{domain}"


def _generate_otp() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _send_otp_email(user: User, code: str) -> None:
    send_email(
        to=user.email,
        subject="Votre code de connexion Globex FedEx",
        body_text=(
            f"Bonjour {user.full_name},\n\n"
            f"Votre code de vérification est : {code}\n\n"
            f"Ce code expire dans {OTP_TTL_MINUTES} minutes.\n"
            "Si vous n'avez pas tenté de vous connecter, ignorez cet email.\n\n"
            "L'équipe Globex FedEx."
        ),
        body_html=(
            f"<p>Bonjour {user.full_name},</p>"
            "<p>Voici votre code de vérification pour vous connecter :</p>"
            f'<p style="font-size:28px;font-weight:800;letter-spacing:6px;color:#4d148c;">{code}</p>'
            f"<p>Ce code expire dans {OTP_TTL_MINUTES} minutes.</p>"
            "<p style=\"color:#666;font-size:13px;\">"
            "Si vous n'avez pas tenté de vous connecter, ignorez cet email.</p>"
        ),
    )


def create_login_challenge(db: Session, user: User) -> LoginOtpChallenge:
    """Crée un défi 2FA, envoie l'OTP par email et retourne le challenge."""
    # Invalide les anciens défis pour cet utilisateur.
    old = db.scalars(select(LoginOtpChallenge).where(LoginOtpChallenge.user_id == user.id)).all()
    for row in old:
        db.delete(row)

    code = _generate_otp()
    challenge = LoginOtpChallenge(
        user_id=user.id,
        challenge_token=secrets.token_urlsafe(32),
        otp_hash=get_password_hash(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        last_sent_at=datetime.now(timezone.utc),
    )
    db.add(challenge)
    db.flush()
    _send_otp_email(user, code)
    db.commit()
    db.refresh(challenge)
    return challenge


def resend_login_challenge(db: Session, challenge_token: str) -> LoginOtpChallenge:
    """Renvoie un OTP pour un défi existant (avec cooldown)."""
    challenge = db.scalars(
        select(LoginOtpChallenge).where(LoginOtpChallenge.challenge_token == challenge_token.strip())
    ).first()
    if challenge is None:
        raise ValueError("invalid_challenge")
    if challenge.expires_at < datetime.now(timezone.utc):
        raise ValueError("expired")
    if challenge.attempts >= MAX_ATTEMPTS:
        raise ValueError("locked")

    sent = challenge.last_sent_at
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - sent).total_seconds()
    if elapsed < RESEND_COOLDOWN_SECONDS:
        raise ValueError("cooldown")

    user = db.get(User, challenge.user_id)
    if user is None:
        raise ValueError("invalid_challenge")

    code = _generate_otp()
    challenge.otp_hash = get_password_hash(code)
    challenge.expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    challenge.attempts = 0
    challenge.last_sent_at = datetime.now(timezone.utc)
    _send_otp_email(user, code)
    db.commit()
    db.refresh(challenge)
    return challenge


def verify_login_challenge(db: Session, challenge_token: str, code: str) -> User:
    """Vérifie l'OTP et retourne l'utilisateur si valide."""
    challenge = db.scalars(
        select(LoginOtpChallenge).where(LoginOtpChallenge.challenge_token == challenge_token.strip())
    ).first()
    if challenge is None:
        raise ValueError("invalid_challenge")
    if challenge.expires_at < datetime.now(timezone.utc):
        db.delete(challenge)
        db.commit()
        raise ValueError("expired")
    if challenge.attempts >= MAX_ATTEMPTS:
        raise ValueError("locked")

    if not verify_password(code.strip(), challenge.otp_hash):
        challenge.attempts += 1
        if challenge.attempts >= MAX_ATTEMPTS:
            db.delete(challenge)
        db.commit()
        raise ValueError("invalid_code")

    user = db.get(User, challenge.user_id)
    if user is None:
        raise ValueError("invalid_challenge")

    db.delete(challenge)
    db.commit()
    return user
