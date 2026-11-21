"""Pydantic request/response schemas.

These define the API contract: FastAPI validates request bodies against them
(422 on mismatch), filters responses through them (`response_model`), and
publishes them in the OpenAPI schema at /openapi.json.
"""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field

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
    is_done: bool
    archived_at: datetime | None


class MemberSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserPublic
    role: BoardRole
    added_at: datetime


class CardSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    list_id: int
    # Increases on every change. Send it back with PATCH to avoid overwriting someone else's edit.
    version: int
    title: str
    description: str | None
    position: float
    due_at: datetime | None
    completed_at: datetime | None
    archived_at: datetime | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class ListWithCards(ListSchema):
    cards: list[CardSchema]


class BoardDetail(BoardSummary):
    """Everything needed to render a board in one request."""

    lists: list[ListWithCards]
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
    # true makes this the board's done list (unsetting the previous one).
    is_done: bool | None = None


class MoveRequest(BaseModel):
    """Place an item right after a sibling. `after_id: null` moves it to the start.

    The field is required (no default) so "move to start" is always an explicit choice.
    """

    after_id: int | None


# ── Cards ──


class CardCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    # AwareDatetime rejects "2026-12-01T10:00" (no timezone): a naive time is ambiguous for a deadline.
    due_at: AwareDatetime | None = None


class CardUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)  # null clears
    due_at: AwareDatetime | None = None  # null clears
    completed: bool | None = None
    archived: bool | None = None
    # Optional optimistic lock: "my edits are based on this version". If the card has changed
    # since, the update is refused with 409 instead of silently overwriting the other change.
    version: int | None = None


class CardMoveRequest(MoveRequest):
    """Move a card to `list_id` (the same list to reorder), right after card `after_id` (null = top)."""

    list_id: int
