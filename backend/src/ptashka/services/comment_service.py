"""Comments on cards."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ptashka.models.db import Card, Comment, User


def list_comments(db: Session, card: Card) -> list[Comment]:
    """Oldest first, authors loaded in the same query (joinedload: each comment has one author)."""
    stmt = (
        select(Comment)
        .where(Comment.card_id == card.id)
        .options(joinedload(Comment.author))
        .order_by(Comment.created_at, Comment.id)
    )
    return list(db.scalars(stmt))


def add_comment(db: Session, card: Card, author: User, body: str) -> Comment:
    comment = Comment(card_id=card.id, author_id=author.id, body=body)
    db.add(comment)
    db.flush()
    db.refresh(comment)
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
