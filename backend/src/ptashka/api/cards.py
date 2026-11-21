"""Card endpoints addressed by card id (creating a card lives under /api/lists/{id}/cards)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ptashka.api.presenters import card_detail
from ptashka.auth.board_access import CardAccess, card_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardRole
from ptashka.models.schemas import (
    CardDetail,
    CardMoveRequest,
    CardUpdateRequest,
    ChecklistItemCreateRequest,
    ChecklistItemSchema,
    CommentListResponse,
    CommentRequest,
    CommentSchema,
)
from ptashka.services import card_service, checklist_service, comment_service, label_service
from ptashka.services.board_service import InvalidMoveError

router = APIRouter(prefix="/api/cards", tags=["cards"])

NO_CONTENT = Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{card_id}", response_model=CardDetail)
def get_card(access: CardAccess = Depends(card_access(BoardRole.VIEWER)), db: Session = Depends(get_db)) -> CardDetail:
    return card_detail(db, access.card)


@router.patch("/{card_id}", response_model=CardDetail)
def update_card(
    request: CardUpdateRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> CardDetail:
    """Edit fields. `completed` / `archived` take booleans; `description` / `due_at` can be cleared with null.

    Send the `version` you loaded to get a 409 instead of overwriting a change made since.
    """
    try:
        card = card_service.update_card(db, access.card, request.model_dump(exclude_unset=True))
    except card_service.VersionConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(e), "current_version": e.current_version},
        )
    return card_detail(db, card)


@router.post("/{card_id}/move", response_model=CardDetail)
def move_card(
    request: CardMoveRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> CardDetail:
    """Move within a list or to another list on the same board."""
    try:
        card = card_service.move_card(db, access.card, request.list_id, request.after_id)
    except InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return card_detail(db, card)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    """Delete permanently. Prefer archiving (`PATCH {"archived": true}`)."""
    card_service.delete_card(db, access.card)
    return NO_CONTENT


# ── Labels and assignees ──
# PUT adds, DELETE removes; both are idempotent, so a client (or agent) can retry them safely:
# PUT on a label the card already has, or DELETE on one it doesn't, just succeeds.


@router.put("/{card_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_label(
    label_id: int, access: CardAccess = Depends(card_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    try:
        label_service.attach(db, access.card, label_id)
    except label_service.LabelNotOnBoardError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return NO_CONTENT


@router.delete("/{card_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_label(
    label_id: int, access: CardAccess = Depends(card_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    label_service.detach(db, access.card, label_id)
    return NO_CONTENT


@router.put("/{card_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def assign(
    user_id: int, access: CardAccess = Depends(card_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    """Assign a board member (any role) to the card."""
    try:
        card_service.assign(db, access.card, user_id)
    except card_service.NotAMemberError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return NO_CONTENT


@router.delete("/{card_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign(
    user_id: int, access: CardAccess = Depends(card_access(BoardRole.EDITOR)), db: Session = Depends(get_db)
) -> Response:
    card_service.unassign(db, access.card, user_id)
    return NO_CONTENT


# ── Checklist and comments on a card ──


@router.post("/{card_id}/checklist", response_model=ChecklistItemSchema, status_code=status.HTTP_201_CREATED)
def add_checklist_item(
    request: ChecklistItemCreateRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> ChecklistItemSchema:
    """Add an item at the end of the card's checklist."""
    return ChecklistItemSchema.model_validate(checklist_service.add_item(db, access.card, request.text))


@router.get("/{card_id}/comments", response_model=CommentListResponse)
def list_comments(
    access: CardAccess = Depends(card_access(BoardRole.VIEWER)), db: Session = Depends(get_db)
) -> CommentListResponse:
    """Oldest first."""
    comments = comment_service.list_comments(db, access.card)
    return CommentListResponse(comments=[CommentSchema.model_validate(c) for c in comments])


@router.post("/{card_id}/comments", response_model=CommentSchema, status_code=status.HTTP_201_CREATED)
def add_comment(
    request: CommentRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> CommentSchema:
    comment = comment_service.add_comment(db, access.card, access.access.user, request.body)
    return CommentSchema.model_validate(comment)
