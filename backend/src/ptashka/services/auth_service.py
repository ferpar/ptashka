"""Account lifecycle: registration, login, token refresh, admin approval.

Services hold the business rules and know nothing about HTTP: they raise plain
Python exceptions and the routers in `api/` translate them into status codes.
That keeps the rules easy to test and reuse (the CLI calls them too).
"""

import secrets
from datetime import datetime, timezone
from functools import cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.auth.jwt import create_access_token, hash_refresh_token, new_refresh_token
from ptashka.auth.password import hash_password, verify_password
from ptashka.models.db import RefreshToken, User, UserRole, UserStatus


class UserExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AccountNotActiveError(Exception):
    """Correct credentials, but the account is pending approval or disabled."""

    def __init__(self, status: UserStatus):
        self.status = status
        super().__init__(f"Account is {status.value}")


class InvalidRefreshTokenError(Exception):
    pass


@cache
def _dummy_hash() -> str:
    """A real bcrypt hash of a random secret, computed once on first use: checking a password against
    it costs exactly as much as checking a real one, and nothing can ever match it."""
    return hash_password(secrets.token_urlsafe(32))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, email: str, password: str, display_name: str) -> User:
    """Create a PENDING account. An admin must activate it before it can log in."""
    email = normalize_email(email)
    # bcrypt first (~170 ms of CPU): the session only takes a database connection at its first
    # query, so hashing before any query means no connection sits idle while we hash.
    hashed = hash_password(password)
    if db.scalar(select(User).where(User.email == email)):
        raise UserExistsError("Email already registered")
    user = User(
        email=email,
        hashed_password=hashed,
        display_name=display_name.strip(),
        role=UserRole.USER,
        status=UserStatus.PENDING,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # Always run bcrypt, against a dummy hash if the email is unknown. Otherwise unknown emails would
    # be rejected in ~5 ms and known ones in ~170 ms, and that timing difference alone would reveal
    # which emails are registered (a timing attack).
    password_ok = verify_password(password, user.hashed_password if user else _dummy_hash())
    if user is None or not password_ok:
        raise InvalidCredentialsError("Invalid email or password")
    # Checked only after the password, so this can't be used to probe which emails exist.
    if user.status != UserStatus.ACTIVE:
        raise AccountNotActiveError(user.status)
    return user


def create_tokens(db: Session, user: User) -> tuple[str, str]:
    """Issue an access token and a stored (hashed) refresh token."""
    refresh_token, expires_at = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_refresh_token(refresh_token), expires_at=expires_at))
    db.flush()
    return create_access_token(user.id), refresh_token


def refresh_access_token(db: Session, refresh_token: str) -> str:
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token)))
    if stored is None or stored.revoked:
        raise InvalidRefreshTokenError("Invalid refresh token")
    if stored.expires_at < datetime.now(timezone.utc):  # UTCDateTime: always aware, even on SQLite.
        raise InvalidRefreshTokenError("Refresh token expired")
    if stored.user.status != UserStatus.ACTIVE:
        raise InvalidRefreshTokenError("User is not active")
    return create_access_token(stored.user_id)


def revoke_refresh_token(db: Session, refresh_token: str) -> bool:
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token)))
    if stored is None:
        return False
    stored.revoked = True
    db.flush()
    return True


def update_user_access(db: Session, user: User, status: UserStatus | None, role: UserRole | None) -> User:
    """Admin action: activate/disable an account and/or change its role."""
    if role is not None:
        user.role = role
    if status is not None and status != user.status:
        user.status = status
        if status == UserStatus.ACTIVE and user.approved_at is None:
            user.approved_at = datetime.now(timezone.utc)
        if status != UserStatus.ACTIVE:
            # Sign the user out everywhere.
            for token in user.refresh_tokens:
                token.revoked = True
    db.flush()
    db.refresh(user)
    return user
