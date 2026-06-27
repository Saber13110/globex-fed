import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user_session import UserSession
from app.models.user import User, UserRole, UserStatus
from app.routes.deps import get_current_user
from app.schemas.auth import (
    GoogleAuthConfigResponse,
    GoogleLoginRequest,
    LoginRequest,
    LoginResponse,
    QrLoginPayloadResponse,
    QrLoginRequest,
    Resend2FARequest,
    Token,
    Verify2FARequest,
)
from app.services.activity_log_service import client_ip, write_log
from app.services.preference_service import get_preferences_state, submit_user_preferences
from app.services.quota_service import build_quota_status
from app.services.rate_limit_service import check_rate_limit, clear_keys, record_attempt
from app.services.qr_login_service import (
    find_user_by_qr_token,
    get_or_create_qr_login_token,
    regenerate_qr_login_token,
    validate_user_for_qr_login,
)
from app.services.two_factor_service import (
    create_login_challenge,
    is_two_factor_active,
    mask_email,
    resend_login_challenge,
    verify_login_challenge,
)
from app.schemas.preference import PreferenceSubmitRequest, UserPreferencesState
from app.schemas.quota import QuotaLimitsRead, QuotaUsageRead, UserQuotaStatus
from app.schemas.user import (
    AccountOverview,
    ActivateRequest,
    EmployeeSignupResponse,
    UserCreate,
    UserRead,
    UserSessionRead,
    UserPreferencesUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _parse_user_agent(user_agent: str) -> tuple[str, str]:
    ua = user_agent.lower()
    browser = "Unknown"
    if "edg/" in ua:
        browser = "Edge"
    elif "chrome/" in ua:
        browser = "Chrome"
    elif "firefox/" in ua:
        browser = "Firefox"
    elif "safari/" in ua and "chrome/" not in ua:
        browser = "Safari"

    machine = "Unknown"
    if "windows" in ua:
        machine = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        machine = "macOS"
    elif "android" in ua:
        machine = "Android"
    elif "iphone" in ua or "ipad" in ua:
        machine = "iOS"
    elif "linux" in ua:
        machine = "Linux"
    return browser, machine


def _ensure_organization_id(user: User, db: Session) -> None:
    if user.organization_id and user.organization_id.strip():
        return
    user.organization_id = str(uuid.uuid4())
    db.add(user)
    db.commit()
    db.refresh(user)


def _ensure_active_session_for_user(user: User, request: Request, db: Session) -> None:
    row = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id, UserSession.is_active.is_(True))
        .order_by(UserSession.updated_at.desc())
        .first()
    )
    if row is not None:
        return
    ua = request.headers.get("user-agent", "")
    browser, machine = _parse_user_agent(ua)
    location = request.client.host if request.client else "Unknown"
    fallback_token_id = f"legacy-{user.id}"
    existing = db.query(UserSession).filter(UserSession.token_id == fallback_token_id).one_or_none()
    if existing is None:
        row = UserSession(
            user_id=user.id,
            token_id=fallback_token_id,
            browser=browser,
            machine=machine,
            location=location,
            is_active=True,
        )
        db.add(row)
    else:
        existing.is_active = True
        existing.browser = browser
        existing.machine = machine
        existing.location = location
    db.commit()


def _login_rate_keys(request: Request, email: str) -> tuple[str, str]:
    ip = client_ip(request) or "unknown"
    return f"login:ip:{ip}", f"login:email:{str(email).lower()}"


def _enforce_login_rate_limit(request: Request, email: str) -> None:
    settings = get_settings()
    for key in _login_rate_keys(request, email):
        check_rate_limit(
            key,
            max_attempts=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )


def _record_failed_login(request: Request, email: str) -> None:
    settings = get_settings()
    for key in _login_rate_keys(request, email):
        record_attempt(key, window_seconds=settings.login_rate_limit_window_seconds)


def _log_auth_failure(
    db: Session,
    request: Request,
    *,
    email: str,
    reason: str,
    user_id: int | None = None,
) -> None:
    _record_failed_login(request, email)
    write_log(
        db,
        action="auth.login_failed",
        message=f"Échec connexion ({reason}) — {mask_email(email)}",
        category="auth",
        level="WARNING",
        user_id=user_id,
        ip_address=client_ip(request),
        metadata={"reason": reason},
        commit=False,
    )


def _issue_session_token(
    user: User,
    request: Request,
    db: Session,
    *,
    login_method: str = "password",
) -> Token:
    token_id = uuid.uuid4().hex
    token = create_access_token(subject=str(user.id), token_id=token_id)
    ua = request.headers.get("user-agent", "")
    browser, machine = _parse_user_agent(ua)
    location = request.client.host if request.client else "Unknown"
    from app.services.user_notification_service import maybe_notify_new_login_device

    if user.role != UserRole.admin.value:
        maybe_notify_new_login_device(
            db,
            user_id=user.id,
            browser=browser,
            machine=machine,
            ip=location,
        )
    row = UserSession(
        user_id=user.id,
        token_id=token_id,
        browser=browser,
        machine=machine,
        location=location,
        is_active=True,
    )
    db.add(row)
    ip_key, email_key = _login_rate_keys(request, user.email)
    clear_keys(ip_key, email_key)
    write_log(
        db,
        action="auth.login",
        message=f"Connexion réussie ({user.role})",
        category="auth",
        level="SUCCESS",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"browser": browser, "machine": machine, "method": login_method},
        commit=False,
    )
    db.commit()
    return Token(access_token=token)


def _verify_google_id_token(id_token: str, nonce: str | None = None) -> dict:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Impossible de vérifier le jeton Google.",
        ) from exc

    settings = get_settings()
    aud = str(data.get("aud", "")).strip()
    if settings.google_client_id and aud != settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jeton Google invalide (audience).")

    iss = str(data.get("iss", "")).strip()
    if iss not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jeton Google invalide (issuer).")

    exp_raw = str(data.get("exp", "0")).strip()
    try:
        exp = int(exp_raw)
    except ValueError:
        exp = 0
    if exp <= int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jeton Google expiré.")

    if nonce:
        token_nonce = str(data.get("nonce", "")).strip()
        if token_nonce and token_nonce != nonce:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nonce Google invalide.")

    email = str(data.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email absent du profil Google.")
    if str(data.get("email_verified", "")).lower() not in {"true", "1"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email Google non vérifié.")

    return data


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> User:
    existing = db.scalars(select(User).where(User.email == str(payload.email))).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email déjà utilisé")

    user = User(
        full_name=payload.full_name,
        email=str(payload.email).lower(),
        password_hash=get_password_hash(payload.password),
        role=UserRole.client.value,
        preferred_language=payload.preferred_language,
        organization_id=str(uuid.uuid4()),
    )
    db.add(user)
    write_log(
        db,
        action="auth.register",
        message=f"Inscription client : {mask_email(user.email)}",
        category="auth",
        level="SUCCESS",
        user_id=None,
        ip_address=client_ip(request),
        metadata={"role": UserRole.client.value},
        commit=False,
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/register/employee", response_model=EmployeeSignupResponse, status_code=status.HTTP_201_CREATED)
def register_employee(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> EmployeeSignupResponse:
    """Inscription d'un employé : crée un compte EN ATTENTE de validation par l'administrateur.

    Le compte ne peut pas se connecter tant qu'il n'a pas été validé puis activé via l'email.
    """
    email = str(payload.email).lower()
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email déjà utilisé")

    user = User(
        full_name=payload.full_name,
        email=email,
        password_hash=get_password_hash(payload.password),
        role=UserRole.employe.value,
        status=UserStatus.pending.value,
        preferred_language=payload.preferred_language,
        organization_id=str(uuid.uuid4()),
    )
    db.add(user)
    write_log(
        db,
        action="auth.register",
        message=f"Demande inscription employé : {mask_email(user.email)}",
        category="auth",
        level="INFO",
        user_id=None,
        ip_address=client_ip(request),
        metadata={"role": UserRole.employe.value, "status": UserStatus.pending.value},
        commit=False,
    )
    db.commit()
    db.refresh(user)
    return EmployeeSignupResponse(
        detail=(
            "Votre demande a bien été enregistrée. Un administrateur doit la valider : "
            "vous recevrez ensuite un email pour vous connecter avec vos identifiants."
        ),
        email=user.email,
        status=user.status,
    )


@router.post("/activate", response_model=UserRead)
def activate_account(payload: ActivateRequest, request: Request, db: Session = Depends(get_db)) -> User:
    """Active un compte employé via le token reçu par email (clic sur le lien d'invitation)."""
    user = db.scalars(select(User).where(User.activation_token == payload.token.strip())).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ce lien n'est plus valide. Si votre compte a déjà été validé, connectez-vous directement.",
        )
    if user.status == UserStatus.active.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce compte est déjà activé.")
    if user.activation_expires_at is not None and user.activation_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ce lien d'activation a expiré.")

    user.status = UserStatus.active.value
    user.activation_token = None
    user.activation_expires_at = None
    write_log(
        db,
        action="auth.activate",
        message=f"Compte activé : {mask_email(user.email)}",
        category="auth",
        level="SUCCESS",
        user_id=user.id,
        ip_address=client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    email = str(payload.email).lower()
    _enforce_login_rate_limit(request, email)

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not verify_password(payload.password, user.password_hash if user else ""):
        _log_auth_failure(db, request, email=email, reason="invalid_credentials", user_id=user.id if user else None)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides")
    if user.status == UserStatus.pending.value:
        _log_auth_failure(db, request, email=email, reason="account_pending", user_id=user.id)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte est en attente de validation par un administrateur.",
        )
    if user.status == UserStatus.invited.value:
        _log_auth_failure(db, request, email=email, reason="account_invited", user_id=user.id)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte a été validé : connectez-vous avec l'email et le mot de passe choisis à l'inscription.",
        )
    if user.status == UserStatus.suspended.value:
        _log_auth_failure(db, request, email=email, reason="account_suspended", user_id=user.id)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte a été suspendu pour des raisons de sécurité. Contactez l'administrateur.",
        )

    if is_two_factor_active(db) and user.role != UserRole.admin.value:
        try:
            challenge = create_login_challenge(db, user)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Impossible d'envoyer le code de vérification : {exc}",
            ) from exc
        write_log(
            db,
            action="auth.2fa_challenge",
            message=f"Code 2FA envoyé à {mask_email(user.email)}",
            category="auth",
            level="INFO",
            user_id=user.id,
            ip_address=client_ip(request),
            commit=False,
        )
        db.commit()
        return LoginResponse(
            requires_2fa=True,
            challenge_token=challenge.challenge_token,
            masked_email=mask_email(user.email),
            detail=f"Un code de vérification a été envoyé à {mask_email(user.email)}.",
        )

    token = _issue_session_token(user, request, db, login_method="password")
    return LoginResponse(access_token=token.access_token, requires_2fa=False)


@router.get("/google/config", response_model=GoogleAuthConfigResponse)
def google_auth_config() -> GoogleAuthConfigResponse:
    settings = get_settings()
    enabled = bool(settings.google_client_id.strip())
    return GoogleAuthConfigResponse(enabled=enabled, client_id=settings.google_client_id if enabled else None)


@router.post("/google", response_model=Token)
def login_with_google(payload: GoogleLoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    settings = get_settings()
    if not settings.google_client_id.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Connexion Google non configurée sur le serveur.",
        )

    claims = _verify_google_id_token(payload.id_token, payload.nonce)
    email = str(claims.get("email", "")).strip().lower()
    full_name = str(claims.get("name", "")).strip() or email.split("@")[0]

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(
            full_name=full_name[:255],
            email=email,
            password_hash=get_password_hash(uuid.uuid4().hex),
            role=UserRole.client.value,
            preferred_language="fr",
            organization_id=str(uuid.uuid4()),
            status=UserStatus.active.value,
        )
        db.add(user)
        db.flush()
        write_log(
            db,
            action="auth.register_google",
            message=f"Inscription Google : {mask_email(user.email)}",
            category="auth",
            level="SUCCESS",
            user_id=user.id,
            ip_address=client_ip(request),
            commit=False,
        )
    elif user.status == UserStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte est en attente de validation par un administrateur.",
        )
    elif user.status == UserStatus.invited.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte a été validé : connectez-vous avec l'email et le mot de passe choisis à l'inscription.",
        )
    elif user.status == UserStatus.suspended.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte a été suspendu pour des raisons de sécurité. Contactez l'administrateur.",
        )

    return _issue_session_token(user, request, db, login_method="google")


@router.post("/2fa/verify", response_model=Token)
def verify_2fa(payload: Verify2FARequest, request: Request, db: Session = Depends(get_db)) -> Token:
    try:
        user = verify_login_challenge(db, payload.challenge_token, payload.code)
    except ValueError as exc:
        code = str(exc)
        write_log(
            db,
            action="auth.2fa_failed",
            message=f"Échec vérification 2FA ({code})",
            category="auth",
            level="WARNING",
            ip_address=client_ip(request),
            metadata={"reason": code},
            commit=True,
        )
        if code == "expired":
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Code expiré. Reconnectez-vous.") from exc
        if code == "locked":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de tentatives. Reconnectez-vous.",
            ) from exc
        if code == "invalid_code":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code incorrect.") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session de vérification invalide.") from exc

    if user.status == UserStatus.suspended.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte a été suspendu pour des raisons de sécurité. Contactez l'administrateur.",
        )

    return _issue_session_token(user, request, db, login_method="2fa")


@router.post("/2fa/resend")
def resend_2fa(payload: Resend2FARequest, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        challenge = resend_login_challenge(db, payload.challenge_token)
        user = db.get(User, challenge.user_id)
        masked = mask_email(user.email) if user else "votre email"
        write_log(
            db,
            action="auth.2fa_resend",
            message=f"Code 2FA renvoyé à {masked}",
            category="auth",
            level="INFO",
            user_id=user.id if user else None,
            ip_address=client_ip(request),
            commit=True,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "cooldown":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Veuillez patienter avant de renvoyer un code.",
            ) from exc
        if code == "expired":
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session expirée. Reconnectez-vous.") from exc
        if code == "locked":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de tentatives. Reconnectez-vous.",
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session invalide.") from exc

    return {"detail": f"Un nouveau code a été envoyé à {masked}."}


@router.get("/me/qr-login", response_model=QrLoginPayloadResponse)
def get_my_qr_login(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QrLoginPayloadResponse:
    """Retourne le payload QR (création automatique la première fois)."""
    if current_user.role not in (UserRole.client.value, UserRole.employe.value):
        return QrLoginPayloadResponse(can_use_qr=False, has_active_qr=False)
    if current_user.status != UserStatus.active.value:
        return QrLoginPayloadResponse(can_use_qr=False, has_active_qr=False)

    try:
        payload, created = get_or_create_qr_login_token(db, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Compte non éligible au QR.") from exc

    if created:
        return QrLoginPayloadResponse(payload=payload, has_active_qr=True, can_use_qr=True)
    return QrLoginPayloadResponse(payload=None, has_active_qr=True, can_use_qr=True)


@router.post("/me/qr-login/regenerate", response_model=QrLoginPayloadResponse)
def regenerate_my_qr_login(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QrLoginPayloadResponse:
    """Régénère le code QR personnel (invalide l'ancien)."""
    if current_user.role not in (UserRole.client.value, UserRole.employe.value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="QR réservé aux clients et employés.")
    try:
        payload = regenerate_qr_login_token(db, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Compte non éligible au QR.") from exc
    return QrLoginPayloadResponse(payload=payload, has_active_qr=True, can_use_qr=True)


@router.post("/qr-login", response_model=Token)
def login_with_qr(payload: QrLoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    """Connexion via scan du QR personnel (sans email/mot de passe, sans 2FA)."""
    user = find_user_by_qr_token(db, payload.payload)
    if user is None:
        write_log(
            db,
            action="auth.qr_login_failed",
            message="Code QR invalide",
            category="auth",
            level="WARNING",
            ip_address=client_ip(request),
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code QR invalide.")
    try:
        validate_user_for_qr_login(user)
    except ValueError as exc:
        code = str(exc)
        write_log(
            db,
            action="auth.qr_login_failed",
            message=f"Connexion QR refusée ({code})",
            category="auth",
            level="WARNING",
            user_id=user.id,
            ip_address=client_ip(request),
            metadata={"reason": code},
            commit=True,
        )
        if code == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte en attente de validation administrateur.",
            ) from exc
        if code == "admin_not_allowed":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Connexion QR non disponible.") from exc
        if code == "suspended":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Votre compte a été suspendu pour des raisons de sécurité. Contactez l'administrateur.",
            ) from exc
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte non actif.") from exc

    return _issue_session_token(user, request, db, login_method="qr")


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    _ensure_organization_id(current_user, db)
    return current_user


@router.get("/me/preferences", response_model=UserPreferencesState)
def get_my_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesState:
    return get_preferences_state(db, current_user)


@router.post("/me/preferences/submit", response_model=UserPreferencesState)
def submit_my_preferences(
    payload: PreferenceSubmitRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesState:
    try:
        row = submit_user_preferences(db, current_user, payload)
    except HTTPException:
        write_log(
            db,
            action="security.preference_blocked",
            message="Soumission de préférences bloquée par la politique de sécurité",
            category="system",
            level="WARNING",
            user_id=current_user.id,
            ip_address=client_ip(request),
            commit=True,
        )
        raise
    write_log(
        db,
        action="user.preference_submitted",
        message="Préférences IA soumises pour validation admin",
        category="auth",
        level="INFO",
        user_id=current_user.id,
        ip_address=client_ip(request),
        metadata={"submission_id": row.id, "risk_score": row.risk_score},
        commit=False,
    )
    db.commit()
    return get_preferences_state(db, current_user)


@router.get("/quota", response_model=UserQuotaStatus)
def my_quota(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserQuotaStatus:
    """Quotas journaliers et consommation du jour pour l'utilisateur connecté."""
    raw = build_quota_status(db, current_user)
    return UserQuotaStatus(
        limits=QuotaLimitsRead(**raw["limits"]),
        usage=QuotaUsageRead(**raw["usage"]),
        remaining=QuotaLimitsRead(**raw["remaining"]),
        exempt=raw["exempt"],
    )


@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserPreferencesUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    changes: list[str] = []
    if payload.preferred_language is not None:
        lang = payload.preferred_language.strip().lower()
        if lang not in {"fr", "en", "ar"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Langue non supportée.")
        if lang != current_user.preferred_language:
            current_user.preferred_language = lang
            changes.append("langue")
    if changes:
        write_log(
            db,
            action="user.profile_update",
            message=f"Profil mis à jour ({', '.join(changes)})",
            category="auth",
            level="INFO",
            user_id=current_user.id,
            ip_address=client_ip(request),
            metadata={"fields": changes},
            commit=False,
        )
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/account-overview", response_model=AccountOverview)
def account_overview(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOverview:
    _ensure_organization_id(current_user, db)
    _ensure_active_session_for_user(current_user, request, db)
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == current_user.id, UserSession.is_active.is_(True))
        .order_by(UserSession.updated_at.desc())
        .all()
    )
    return AccountOverview(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        sessions=[UserSessionRead.model_validate(s) for s in sessions],
    )


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    rows = db.query(UserSession).filter(UserSession.user_id == current_user.id, UserSession.is_active.is_(True)).all()
    count = len(rows)
    for row in rows:
        row.is_active = False
    write_log(
        db,
        action="auth.logout_all",
        message=f"Déconnexion de toutes les sessions ({count})",
        category="auth",
        level="INFO",
        user_id=current_user.id,
        ip_address=client_ip(request),
        metadata={"sessions_closed": count},
        commit=False,
    )
    db.commit()


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    write_log(
        db,
        action="user.account_delete",
        message=f"Suppression du compte : {mask_email(current_user.email)}",
        category="auth",
        level="WARNING",
        user_id=current_user.id,
        ip_address=client_ip(request),
        commit=False,
    )
    db.delete(current_user)
    db.commit()
