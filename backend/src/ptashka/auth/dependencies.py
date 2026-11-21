"""FastAPI authentication dependencies.

An endpoint declares `user: User = Depends(get_current_user)` and FastAPI runs
this code first: read the `Authorization: Bearer ...` header, verify the credential,
load the user. If anything fails it raises, and the endpoint never runs.

Two kinds of credential are accepted in the same header:
- a JWT access token, from logging in with a password (an *interactive* session);
- a personal API token (`ptk_...`), for scripts and agents. Read-scoped tokens may
  only make safe requests (GET/HEAD/OPTIONS), and no API token may manage tokens or
  use admin endpoints (see `require_interactive`).
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ptashka.auth.jwt import TokenError, decode_access_token
from ptashka.db.database import DbSession
from ptashka.models.db import ApiToken, TokenScope, User, UserRole, UserStatus
from ptashka.services import token_service

# Also adds the "Authorize" button to the /docs page.
security = HTTPBearer()

# Methods that never change anything in this API. A read-scoped token is limited to these.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass
class AuthContext:
    user: User
    token: ApiToken | None  # None: an interactive session (JWT from a password login).


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth(
    request: Request,
    db: DbSession,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext:
    """Who is calling, and how. FastAPI caches it per request, so it runs once however many
    dependencies ask for it."""
    raw = credentials.credentials
    if token_service.looks_like_api_token(raw):
        token = token_service.resolve(db, raw)
        if token is None:
            raise _unauthorized("Invalid, expired or revoked API token")
        if token.scope == TokenScope.READ and request.method not in SAFE_METHODS:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This API token is read-only")
        return AuthContext(user=token.user, token=token)

    try:
        user_id = decode_access_token(raw)
    except TokenError as e:
        raise _unauthorized(str(e))
    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("User not found")
    if user.status != UserStatus.ACTIVE:
        raise _unauthorized("User is not active")
    return AuthContext(user=user, token=None)


def get_current_user(auth: AuthContext = Depends(get_auth)) -> User:
    """The authenticated, *active* user, however they authenticated."""
    return auth.user


def require_interactive(auth: AuthContext = Depends(get_auth)) -> User:
    """For sensitive actions: a password login is required, an API token isn't enough.

    Otherwise a leaked read token could mint itself a write token, or an agent could approve accounts.
    """
    if auth.token is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not available with an API token: log in with a password"
        )
    return auth.user


def require_admin(user: User = Depends(require_interactive)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user
