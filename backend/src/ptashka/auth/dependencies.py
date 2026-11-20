"""FastAPI authentication dependencies.

An endpoint declares `user: User = Depends(get_current_user)` and FastAPI runs
this code first: read the `Authorization: Bearer ...` header, verify the token,
load the user. If anything fails it raises, and the endpoint never runs.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ptashka.auth.jwt import TokenError, decode_access_token
from ptashka.db.database import get_db
from ptashka.models.db import User, UserRole, UserStatus

# Also adds the "Authorize" button to the /docs page.
security = HTTPBearer()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """The authenticated, *active* user. Pending or disabled accounts get a 401."""
    try:
        user_id = decode_access_token(credentials.credentials)
    except TokenError as e:
        raise _unauthorized(str(e))

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("User not found")
    if user.status != UserStatus.ACTIVE:
        raise _unauthorized("User is not active")
    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Dependency factory: the current user, provided they hold one of `roles`."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


require_admin = require_role(UserRole.ADMIN)
