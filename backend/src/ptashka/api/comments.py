"""Comment endpoints addressed by comment id (listing and adding live under /api/cards/{id}/comments).

Permissions go beyond board roles here:
- Editing: only the author. Nobody, not even an owner, can put words in someone else's mouth.
- Deleting: the author, or a board owner (moderation).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import CommentAccess, comment_access
from ptashka.db.database import get_db
from ptashka.models.db import BoardRole
from ptashka.models.schemas import CommentRequest, CommentSchema
from ptashka.services import comment_service

router = APIRouter(prefix="/api/comments", tags=["comments"])


def _is_author(access: CommentAccess) -> bool:
    return access.comment.author_id == access.access.user.id


@router.patch("/{comment_id}", response_model=CommentSchema)
def edit_comment(
    request: CommentRequest,
    access: CommentAccess = Depends(comment_access(BoardRole.CONTRIBUTOR)),
    db: Session = Depends(get_db),
) -> CommentSchema:
    if not _is_author(access):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author can edit a comment")
    return CommentSchema.model_validate(comment_service.edit_comment(db, access.comment, request.body))


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    # VIEWER here, then decide: authors may delete their own comments even if since demoted to viewer.
    access: CommentAccess = Depends(comment_access(BoardRole.VIEWER)),
    db: Session = Depends(get_db),
) -> Response:
    if not (_is_author(access) or access.access.role.includes(BoardRole.OWNER)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author or a board owner can delete it")
    comment_service.delete_comment(db, access.comment)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
