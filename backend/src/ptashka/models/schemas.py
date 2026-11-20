"""Pydantic request/response schemas.

These define the API contract: FastAPI validates request bodies against them
(422 on mismatch), filters responses through them (`response_model`), and
publishes them in the OpenAPI schema at /openapi.json.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ptashka.models.db import UserRole, UserStatus

# ── Auth ──


class UserSchema(BaseModel):
    # from_attributes lets `UserSchema.model_validate(user)` read a SQLAlchemy object.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    # bcrypt only looks at the first 72 bytes and bcrypt>=5 rejects longer input.
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    # Not EmailStr: login only needs a lookup key, and format rules belong to registration.
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: UserSchema
    tokens: TokenResponse


class RegisterResponse(BaseModel):
    """Registration never logs in: new accounts wait for admin approval."""

    user: UserSchema
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


# ── Admin ──


class UserListResponse(BaseModel):
    users: list[UserSchema]


class AdminUserUpdateRequest(BaseModel):
    status: UserStatus | None = None
    role: UserRole | None = None
