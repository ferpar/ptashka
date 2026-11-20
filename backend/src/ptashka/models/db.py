"""SQLAlchemy database models.

Groups:

- **Accounts**: User, RefreshToken.
- **Boards**: Board, BoardMember (who can see/edit a board), BoardList (a column).
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all models. `Base.metadata` knows every table."""


def _enum(cls: type[PyEnum]) -> Enum:
    """Store enums by value (lowercase strings), not by member name, and as a plain
    VARCHAR rather than a native Postgres ENUM, so adding a member needs no migration."""
    return Enum(cls, values_callable=lambda e: [m.value for m in e], native_enum=False, length=20)


# ── Accounts ──


class UserRole(str, PyEnum):
    """Site-wide role. Board permissions are separate (BoardMember.role, phase 2)."""

    USER = "user"
    ADMIN = "admin"


class UserStatus(str, PyEnum):
    """Open sign-up creates PENDING accounts; an admin activates them."""

    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), default=UserRole.USER)
    status: Mapped[UserStatus] = mapped_column(_enum(UserStatus), default=UserStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SHA-256 of the token: a database leak must not yield usable refresh tokens.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


# ── Boards ──


class BoardRole(str, PyEnum):
    """What a member may do on one board. Ordered: each role includes the ones before it."""

    VIEWER = "viewer"  # read everything
    EDITOR = "editor"  # + create/edit/move lists and cards
    OWNER = "owner"  # + rename/archive/delete the board, manage members

    @property
    def rank(self) -> int:
        return list(BoardRole).index(self)

    def includes(self, other: "BoardRole") -> bool:
        return self.rank >= other.rank


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Who created it, for the record. Ownership itself lives in BoardMember.
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Archived boards are hidden from the board list but keep all their data.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    members: Mapped[list["BoardMember"]] = relationship(back_populates="board", cascade="all, delete-orphan")
    lists: Mapped[list["BoardList"]] = relationship(
        back_populates="board", cascade="all, delete-orphan", order_by="BoardList.position"
    )


class BoardMember(Base):
    """A user's access to a board. No row = the board doesn't exist, as far as they know."""

    __tablename__ = "board_members"

    # Composite primary key: a user is a member of a board at most once.
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[BoardRole] = mapped_column(_enum(BoardRole))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    board: Mapped[Board] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class BoardList(Base):
    """A column on a board ("To do", "Doing", ...). Named BoardList so it doesn't shadow Python's `list`."""

    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # Sort key, see services/ordering.py. Gaps are intentional.
    position: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    board: Mapped[Board] = relationship(back_populates="lists")
