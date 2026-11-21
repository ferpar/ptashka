"""Personal API tokens: creation, lookup, revocation.

A token is `ptk_` + 32 random bytes (URL-safe base64). The prefix lets the server tell a token from
a JWT at a glance, and lets secret scanners (e.g. GitHub's) recognise leaked ones. Only a SHA-256
hash is stored: a fast hash is fine because the token is 256 random bits, not a guessable password.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.models.db import ApiToken, TokenScope, User, UserStatus

PREFIX = "ptk_"
SHOWN_PREFIX_LENGTH = len(PREFIX) + 8
# Recording last use on every request would turn every read into a write; once a minute is plenty.
LAST_USED_RESOLUTION = timedelta(minutes=1)


def looks_like_api_token(credential: str) -> bool:
    return credential.startswith(PREFIX)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_token(
    db: Session, user: User, name: str, scope: TokenScope, expires_in_days: int | None = None
) -> tuple[ApiToken, str]:
    """Returns the stored token and the raw secret. The secret can't be recovered later."""
    raw = PREFIX + secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days) if expires_in_days else None
    token = ApiToken(
        user_id=user.id,
        name=name.strip(),
        prefix=raw[:SHOWN_PREFIX_LENGTH],
        token_hash=_hash(raw),
        scope=scope,
        expires_at=expires_at,
    )
    db.add(token)
    db.flush()
    db.refresh(token)
    return token, raw


def tokens_for_user(db: Session, user: User) -> list[ApiToken]:
    return list(db.scalars(select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())))


def revoke(db: Session, token: ApiToken) -> None:
    if token.revoked_at is None:  # Idempotent: revoking twice keeps the first timestamp.
        token.revoked_at = datetime.now(timezone.utc)
        db.flush()


def resolve(db: Session, raw: str) -> ApiToken | None:
    """The valid token for this secret, or None (unknown, revoked, expired, or its user isn't active)."""
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == _hash(raw)))
    now = datetime.now(timezone.utc)
    if (
        token is None
        or token.revoked_at is not None
        or (token.expires_at is not None and token.expires_at <= now)
        or token.user.status != UserStatus.ACTIVE
    ):
        return None
    if token.last_used_at is None or now - token.last_used_at >= LAST_USED_RESOLUTION:
        token.last_used_at = now
        db.flush()
    return token
