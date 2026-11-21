"""Comments on cards."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ptashka.models.db import ActivityKind, Card, Comment, User
from ptashka.services import activity_service


def list_comments(db: Session, card: Card) -> list[Comment]:
    """Oldest first, authors loaded in the same query (joinedload: each comment has one author)."""
    stmt = (
        select(Comment)
        .where(Comment.card_id == card.id)
        .options(joinedload(Comment.author))
        .order_by(Comment.created_at, Comment.id)
    )
    return list(db.scalars(stmt))


EXCERPT_LENGTH = 140


def add_comment(db: Session, actor: User, card: Card, body: str) -> Comment:
    comment = Comment(card_id=card.id, author_id=actor.id, body=body)
    db.add(comment)
    db.flush()
    db.refresh(comment)
    excerpt = body if len(body) <= EXCERPT_LENGTH else body[: EXCERPT_LENGTH - 1] + "…"
    activity_service.record(db, actor, ActivityKind.COMMENT_ADDED, card.board_id, card, comment_id=comment.id, excerpt=excerpt)
    return comment


def edit_comment(db: Session, comment: Comment, body: str) -> Comment:
    if body != comment.body:  # Re-saving the same text isn't an edit.
        comment.body = body
        comment.edited_at = datetime.now(timezone.utc)
        db.flush()
        db.refresh(comment)
    return comment


def delete_comment(db: Session, comment: Comment) -> None:
    db.delete(comment)
    db.flush()
