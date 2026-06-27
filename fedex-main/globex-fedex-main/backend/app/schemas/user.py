from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    full_name: str = Field(..., max_length=255)
    email: EmailStr
    preferred_language: str = Field(default="fr", max_length=8)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class ActivateRequest(BaseModel):
    token: str = Field(..., max_length=96)


class EmployeeSignupResponse(BaseModel):
    detail: str
    email: EmailStr
    status: str


class UserRead(UserBase):
    id: int
    organization_id: str
    role: str
    status: str
    response_preferences: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class UserSessionRead(BaseModel):
    id: int
    browser: str
    machine: str
    location: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountOverview(BaseModel):
    user_id: int
    organization_id: str
    sessions: list[UserSessionRead]


class UserPreferencesUpdate(BaseModel):
    preferred_language: str | None = Field(default=None, max_length=8)
    response_preferences: str | None = Field(default=None, max_length=4000)
