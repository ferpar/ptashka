"""List endpoints addressed by list id (creating a list lives under /api/boards/{id}/lists)."""

from fastapi import APIRouter, Depends, HTTPException, status

from ptashka.api.presenters import card_detail
from ptashka.auth.board_access import ListAccess, list_access
from ptashka.db.database import DbSession
from ptashka.models.db import BoardList, BoardRole
from ptashka.models.schemas import CardCreateRequest, CardDetail, ListSchema, ListUpdateRequest, MoveRequest
from ptashka.services import board_service, card_service

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.patch("/{list_id}", response_model=ListSchema)
def update_list(
    db: DbSession,
    request: ListUpdateRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
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
    db.flush()
    db.refresh(board_list)
    return board_list


@router.post("/{list_id}/move", response_model=ListSchema)
def move_list(
    db: DbSession,
    request: MoveRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
) -> BoardList:
    """Reorder: place this list right after `after_id`, or first when `after_id` is null."""
    try:
        return board_service.move_list(db, access.board_list, request.after_id)
    except board_service.InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.post("/{list_id}/cards", response_model=CardDetail, status_code=status.HTTP_201_CREATED)
def create_card(
    db: DbSession,
    request: CardCreateRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
) -> CardDetail:
    """Add a card at the bottom of the list."""
    try:
        card = card_service.create_card(
            db, access.board_list, access.access.user, request.title, request.description, request.due_at
        )
    except board_service.InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return card_detail(db, card)
