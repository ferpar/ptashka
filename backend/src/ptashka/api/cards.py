"""Card endpoints addressed by card id (creating a card lives under /api/lists/{id}/cards)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import CardAccess, card_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardRole, Card
from ptashka.models.schemas import CardMoveRequest, CardSchema, CardUpdateRequest
from ptashka.services import card_service
from ptashka.services.board_service import InvalidMoveError

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("/{card_id}", response_model=CardSchema)
def get_card(access: CardAccess = Depends(card_access(BoardRole.VIEWER))) -> Card:
    return access.card


@router.patch("/{card_id}", response_model=CardSchema)
def update_card(
    request: CardUpdateRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> Card:
    """Edit fields. `completed` / `archived` take booleans; `description` / `due_at` can be cleared with null."""
    return card_service.update_card(db, access.card, request.model_dump(exclude_unset=True))


@router.post("/{card_id}/move", response_model=CardSchema)
def move_card(
    request: CardMoveRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> Card:
    """Move within a list or to another list on the same board."""
    try:
        return card_service.move_card(db, access.card, request.list_id, request.after_id)
    except InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    """Delete permanently. Prefer archiving (`PATCH {"archived": true}`)."""
    card_service.delete_card(db, access.card)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
