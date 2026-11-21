"""Checklist item endpoints addressed by item id (adding one lives under /api/cards/{id}/checklist)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import ChecklistItemAccess, checklist_item_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardRole
from ptashka.models.schemas import ChecklistItemSchema, ChecklistItemUpdateRequest, MoveRequest
from ptashka.services import checklist_service
from ptashka.services.board_service import InvalidMoveError

router = APIRouter(prefix="/api/checklist-items", tags=["checklist"])


@router.patch("/{item_id}", response_model=ChecklistItemSchema)
def update_item(
    request: ChecklistItemUpdateRequest,
    access: ChecklistItemAccess = Depends(checklist_item_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> ChecklistItemSchema:
    """Edit the text, or tick (`done: true`) / untick (`done: false`) the item."""
    item = checklist_service.update_item(db, access.item, request.model_dump(exclude_unset=True))
    return ChecklistItemSchema.model_validate(item)


@router.post("/{item_id}/move", response_model=ChecklistItemSchema)
def move_item(
    request: MoveRequest,
    access: ChecklistItemAccess = Depends(checklist_item_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> ChecklistItemSchema:
    """Reorder within the card's checklist: right after `after_id`, or first when null."""
    try:
        return ChecklistItemSchema.model_validate(checklist_service.move_item(db, access.item, request.after_id))
    except InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    access: ChecklistItemAccess = Depends(checklist_item_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> Response:
    checklist_service.delete_item(db, access.item)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
