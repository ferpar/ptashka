"""SQLAlchemy database models.

Groups:

- **Accounts**: User, RefreshToken.
- **Boards** (phase 2+): Board, BoardMember, List, Card, ...
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
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
