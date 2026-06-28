from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Réponse de connexion : JWT direct ou demande de code 2FA."""

    access_token: str | None = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    challenge_token: str | None = None
    masked_email: str | None = None
    detail: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., min_length=20, max_length=6000)
    nonce: str | None = Field(default=None, max_length=256)


class GoogleAuthConfigResponse(BaseModel):
    enabled: bool
    client_id: str | None = None


class Verify2FARequest(BaseModel):
    challenge_token: str = Field(..., max_length=96)
    code: str = Field(..., min_length=6, max_length=6)


class Resend2FARequest(BaseModel):
    challenge_token: str = Field(..., max_length=96)


class QrLoginPayloadResponse(BaseModel):
    payload: str | None = None
    has_active_qr: bool = False
    can_use_qr: bool = False


class QrLoginRequest(BaseModel):
    payload: str = Field(..., min_length=8, max_length=512)
