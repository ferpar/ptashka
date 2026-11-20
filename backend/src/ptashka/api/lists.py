"""List endpoints addressed by list id (creating a list lives under /api/boards/{id}/lists)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import ListAccess, list_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardList, BoardRole
from ptashka.models.schemas import ListSchema, ListUpdateRequest, MoveRequest
from ptashka.services import board_service

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.patch("/{list_id}", response_model=ListSchema)
def update_list(
    request: ListUpdateRequest,
    access: ListAccess = Depends(list_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> BoardList:
    """Rename, archive (`archived: true`) or restore (`archived: false`) a list."""
    board_list = access.board_list
    changes = request.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes:
        board_list.name = changes["name"].strip()
    if "archived" in changes:
        board_service.set_archived(board_list, changes["archived"])
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
