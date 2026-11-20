"""JWT access tokens and opaque refresh tokens.

- Access token: a short-lived signed JWT. The server can verify it without a
  database lookup, so it can't be revoked early — hence the short lifetime.
- Refresh token: a long-lived random string stored (hashed) in the database,
  so it *can* be revoked (logout, account disabled).
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))


class TokenError(Exception):
    """Raised when token validation fails."""


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Return the user id of a valid access token. Raises TokenError otherwise."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as e:
        raise TokenError(f"Invalid token: {e}") from e
    if payload.get("type") != "access":
        raise TokenError("Invalid token type")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as e:
        raise TokenError("Invalid token payload") from e


def new_refresh_token() -> tuple[str, datetime]:
    """Refresh tokens are opaque random strings, looked up by hash in the database."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return secrets.token_urlsafe(48), expires_at


def hash_refresh_token(token: str) -> str:
    # A fast hash is fine here: the token is 384 random bits, not a guessable password.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
