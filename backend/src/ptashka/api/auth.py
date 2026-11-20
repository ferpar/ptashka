"""Authentication and own-account endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ptashka.auth.dependencies import get_current_user
from ptashka.db.database import get_db
from ptashka.models.db import User, UserStatus
from ptashka.models.schemas import (
    AccessTokenResponse,
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserSchema,
)
from ptashka.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Open sign-up. The account starts pending and cannot log in until an admin approves it."""
    try:
        user = auth_service.register_user(db, request.email, request.password, request.display_name)
    except auth_service.UserExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return RegisterResponse(user=UserSchema.model_validate(user), message="Account created, pending approval")


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Log in. Pending/disabled accounts get a 403 whose detail is `account_pending` / `account_disabled`."""
    try:
        user = auth_service.authenticate_user(db, request.email, request.password)
    except auth_service.InvalidCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except auth_service.AccountNotActiveError as e:
        detail = "account_pending" if e.status == UserStatus.PENDING else "account_disabled"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    access_token, refresh_token = auth_service.create_tokens(db, user)
    return AuthResponse(
        user=UserSchema.model_validate(user),
        tokens=TokenResponse(access_token=access_token, refresh_token=refresh_token),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(request: RefreshTokenRequest, db: Session = Depends(get_db)) -> AccessTokenResponse:
    try:
        access_token = auth_service.refresh_access_token(db, request.refresh_token)
    except auth_service.InvalidRefreshTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return AccessTokenResponse(access_token=access_token)


@router.post("/logout", response_model=MessageResponse)
def logout(request: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    auth_service.revoke_refresh_token(db, request.refresh_token)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserSchema)
def me(user: User = Depends(get_current_user)) -> User:
    # Returning the ORM object is fine: response_model converts it to UserSchema
    # and drops anything not declared there (like hashed_password).
    return user


@router.patch("/me", response_model=UserSchema)
def update_me(
    request: ProfileUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    # exclude_unset: only the fields the client actually sent, so PATCH is a partial update.
    for field, value in request.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
