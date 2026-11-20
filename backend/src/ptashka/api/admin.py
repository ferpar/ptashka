"""Admin endpoints: account approval and roles."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.auth.dependencies import require_admin
from ptashka.db.database import get_db
from ptashka.models.db import User, UserStatus
from ptashka.models.schemas import AdminUserUpdateRequest, UserListResponse, UserSchema
from ptashka.services import auth_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=UserListResponse)
def list_users(
    # `alias` keeps the URL as ?status=pending without shadowing fastapi's `status` module.
    status_filter: UserStatus | None = Query(default=None, alias="status"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListResponse:
    stmt = select(User).order_by(User.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(User.status == status_filter)
    return UserListResponse(users=[UserSchema.model_validate(u) for u in db.scalars(stmt)])


@router.patch("/users/{user_id}", response_model=UserSchema)
def update_user(
    user_id: int,
    request: AdminUserUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """Approve (`status: active`), disable, or change the role of an account."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id and (request.status not in (None, UserStatus.ACTIVE) or request.role not in (None, admin.role)):
        # Prevents an admin from locking themselves (and possibly everyone) out.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot demote or disable themselves")
    return auth_service.update_user_access(db, user, request.status, request.role)
