from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.routes.deps import require_role
from app.schemas.admin import AdminDashboardStats
from app.schemas.system_settings import (
    ChangePasswordRequest,
    IntegrationTestResponse,
    SystemInfoResponse,
    SystemSettingsPatch,
    SystemSettingsRead,
    TestEmailRequest,
)
from app.services.activity_log_service import client_ip, write_log
from app.services.email_service import is_email_configured, send_email
from app.services.system_health_service import build_system_info
from app.services.system_settings_service import load_settings, patch_settings
from app.routes.admin import dashboard_stats

router = APIRouter(tags=["settings"])


@router.get("/stats", response_model=AdminDashboardStats)
def settings_dashboard_stats(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminDashboardStats:
    """Alias KPI pour la page paramètres."""
    return dashboard_stats(admin, db)


@router.get("", response_model=SystemSettingsRead)
def get_settings(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemSettingsRead:
    return load_settings(db)


@router.patch("", response_model=SystemSettingsRead)
def update_settings(
    payload: SystemSettingsPatch,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemSettingsRead:
    result = patch_settings(db, payload)
    write_log(
        db,
        action="settings.update",
        message="Paramètres système mis à jour",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return result


@router.get("/info", response_model=SystemInfoResponse)
def settings_info(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SystemInfoResponse:
    return build_system_info(db)


@router.post("/test-email")
def settings_test_email(
    payload: TestEmailRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not is_email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service email non configuré (vérifiez les variables SMTP_*).",
        )
    try:
        send_email(
            to=payload.to,
            subject="Test — Globex FedEx",
            body_text="Email de test envoyé depuis les paramètres système Globex FedEx.",
            body_html="<p>Email de test envoyé depuis les <strong>paramètres système</strong> Globex FedEx. ✅</p>",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec de l'envoi SMTP : {exc}",
        ) from exc
    write_log(
        db,
        action="settings.test_email",
        message=f"Email de test envoyé à {payload.to}",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return {"sent": True}


@router.post("/change-password")
def settings_change_password(
    payload: ChangePasswordRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Les mots de passe ne correspondent pas.")
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mot de passe actuel incorrect.")
    admin.password_hash = get_password_hash(payload.new_password)
    db.commit()
    write_log(
        db,
        action="settings.change_password",
        message="Mot de passe administrateur modifié",
        category="security",
        level="WARNING",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return {"ok": True}


@router.post("/integrations/fedex/test", response_model=IntegrationTestResponse)
def test_fedex(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> IntegrationTestResponse:
    from app.services.system_health_service import check_fedex

    item = check_fedex()
    return IntegrationTestResponse(
        ok=item.status == "online",
        provider="fedex",
        message=item.detail or item.status,
        latency_ms=item.latency_ms,
    )


@router.post("/integrations/openai/test", response_model=IntegrationTestResponse)
def test_openai(_: User = Depends(require_role("admin"))) -> IntegrationTestResponse:
    settings = get_settings()
    configured = bool(settings.gemini_api_key) and settings.llm_enabled
    return IntegrationTestResponse(
        ok=configured,
        provider="openai",
        message="OpenAI non configuré — utilisez Gemini comme fournisseur principal." if not configured else "Prêt via passerelle LLM.",
        latency_ms=None,
    )


@router.post("/integrations/gemini/test", response_model=IntegrationTestResponse)
def test_gemini(_: User = Depends(require_role("admin"))) -> IntegrationTestResponse:
    from app.services.system_health_service import check_ai

    item = check_ai()
    return IntegrationTestResponse(
        ok=item.status == "online",
        provider="gemini",
        message=item.detail or item.status,
        latency_ms=item.latency_ms,
    )
