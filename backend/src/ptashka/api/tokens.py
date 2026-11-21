"""Personal API tokens. Managing them requires a password login: an API token can't create,
list or revoke tokens (so a leaked read token can't upgrade itself)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ptashka.auth.dependencies import require_interactive
from ptashka.db.database import DbSession
from ptashka.models.db import ApiToken, User
from ptashka.models.schemas import ApiTokenCreated, ApiTokenCreateRequest, ApiTokenListResponse, ApiTokenSchema
from ptashka.services import token_service

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    db: DbSession, request: ApiTokenCreateRequest, user: User = Depends(require_interactive)
) -> ApiTokenCreated:
    """Create a token. **Copy `token` now**: only its hash is stored, it can't be shown again."""
    token, raw = token_service.create_token(db, user, request.name, request.scope, request.expires_in_days)
    return ApiTokenCreated(**ApiTokenSchema.model_validate(token).model_dump(), token=raw)


@router.get("", response_model=ApiTokenListResponse)
def list_tokens(db: DbSession, user: User = Depends(require_interactive)) -> ApiTokenListResponse:
    return ApiTokenListResponse(tokens=[ApiTokenSchema.model_validate(t) for t in token_service.tokens_for_user(db, user)])


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(db: DbSession, token_id: int, user: User = Depends(require_interactive)) -> Response:
    """Revoke immediately. The token stays listed (with `revoked_at`) so you can see what it was."""
    token = db.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:  # Someone else's token looks like a missing one.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    token_service.revoke(db, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
