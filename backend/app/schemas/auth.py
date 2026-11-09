"""Pydantic request/response schemas for authentication."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class InitStatus(BaseModel):
    enrollment_open: bool
    reason: str


class ProviderInitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=1024)

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        if not any(c.isdigit() for c in value) or not any(c.isalpha() for c in value):
            raise ValueError("password must contain letters and digits")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class LoginSuccess(BaseModel):
    csrf_token: str
    user: UserInfo


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    role: str
    is_admin: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=1024)

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        if not any(c.isdigit() for c in value) or not any(c.isalpha() for c in value):
            raise ValueError("password must contain letters and digits")
        return value


class SessionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ip_address: str | None
    user_agent: str | None
    device_id: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    is_current: bool = False


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=1024)

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        if not any(c.isdigit() for c in value) or not any(c.isalpha() for c in value):
            raise ValueError("password must contain letters and digits")
        return value


LoginSuccess.model_rebuild()
