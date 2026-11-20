"""Pydantic request/response schemas.

These define the API contract: FastAPI validates request bodies against them
(422 on mismatch), filters responses through them (`response_model`), and
publishes them in the OpenAPI schema at /openapi.json.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ptashka.models.db import BoardRole, UserRole, UserStatus

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


# ── Boards ──
#
# PATCH requests: a field that's *absent* means "leave it alone"; a field sent
# as null means "clear it" (only where clearing makes sense, like description).
# Routers use `model_dump(exclude_unset=True)` to tell the two apart.


class UserPublic(BaseModel):
    """What other board members may see about a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str


class BoardCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    # Start with "To do / Doing / Done", like most boards do.
    default_lists: bool = True


class BoardUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    # true archives, false restores. Owners only.
    archived: bool | None = None


class BoardSummary(BaseModel):
    id: int
    name: str
    description: str | None
    my_role: BoardRole
    created_at: datetime
    archived_at: datetime | None


class BoardListResponse(BaseModel):
    boards: list[BoardSummary]


class ListSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    name: str
    position: float
    archived_at: datetime | None


class MemberSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserPublic
    role: BoardRole
    added_at: datetime


class BoardDetail(BoardSummary):
    """Everything needed to render a board in one request (cards are added in phase 3)."""

    lists: list[ListSchema]
    members: list[MemberSchema]


class MemberAddRequest(BaseModel):
    email: str = Field(max_length=320)
    role: BoardRole = BoardRole.EDITOR


class MemberUpdateRequest(BaseModel):
    role: BoardRole


class MemberListResponse(BaseModel):
    members: list[MemberSchema]


class ListCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ListUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None


class MoveRequest(BaseModel):
    """Place an item right after a sibling. `after_id: null` moves it to the start.

    The field is required (no default) so "move to start" is always an explicit choice.
    """

    after_id: int | None
