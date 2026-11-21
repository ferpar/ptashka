"""Label endpoints addressed by label id (creating one lives under /api/boards/{id}/labels)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import LabelAccess, label_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardRole
from ptashka.models.schemas import LabelSchema, LabelUpdateRequest
from ptashka.services import label_service

router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.patch("/{label_id}", response_model=LabelSchema)
def update_label(
    request: LabelUpdateRequest,
    access: LabelAccess = Depends(label_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> LabelSchema:
    try:
        label = label_service.update_label(db, access.label, request.model_dump(exclude_unset=True))
    except label_service.LabelExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return LabelSchema.model_validate(label)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    access: LabelAccess = Depends(label_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    """Delete the label and remove it from every card on the board."""
    label_service.delete_label(db, access.label)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
