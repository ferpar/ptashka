"""List endpoints addressed by list id (creating a list lives under /api/boards/{id}/lists)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import ListAccess, list_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardList, BoardRole, Card
from ptashka.models.schemas import CardCreateRequest, CardSchema, ListSchema, ListUpdateRequest, MoveRequest
from ptashka.services import board_service, card_service

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.patch("/{list_id}", response_model=ListSchema)
def update_list(
    request: ListUpdateRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> BoardList:
    """Rename, archive/restore (`archived`), or make it the board's done list (`is_done`)."""
    board_list = access.board_list
    changes = request.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes:
        board_list.name = changes["name"].strip()
    if "archived" in changes:
        board_service.set_archived(board_list, changes["archived"])
    if "is_done" in changes:
        board_service.set_done_list(db, board_list, changes["is_done"])
    db.commit()
    db.refresh(board_list)
    return board_list


@router.post("/{list_id}/move", response_model=ListSchema)
def move_list(
    request: MoveRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> BoardList:
    """Reorder: place this list right after `after_id`, or first when `after_id` is null."""
    try:
        return board_service.move_list(db, access.board_list, request.after_id)
    except board_service.InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.post("/{list_id}/cards", response_model=CardSchema, status_code=status.HTTP_201_CREATED)
def create_card(
    request: CardCreateRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> Card:
    """Add a card at the bottom of the list."""
    try:
        return card_service.create_card(
            db, access.board_list, access.access.user, request.title, request.description, request.due_at
        )
    except board_service.InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
