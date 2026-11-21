"""Board labels, and attaching them to cards."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ptashka.models.db import Board, Card, CardLabel, Label, LabelColor


class LabelExistsError(Exception):
    pass


class LabelNotOnBoardError(Exception):
    pass


def create_label(db: Session, board: Board, name: str, color: LabelColor) -> Label:
    label = Label(board_id=board.id, name=name.strip(), color=color)
    db.add(label)
    _commit_unique_name(db)
    db.refresh(label)
    return label


def update_label(db: Session, label: Label, changes: dict[str, Any]) -> Label:
    if changes.get("name") is not None:
        label.name = changes["name"].strip()
    if changes.get("color") is not None:
        label.color = changes["color"]
    _commit_unique_name(db)
    db.refresh(label)
    return label


def _commit_unique_name(db: Session) -> None:
    """Let the unique constraint decide, rather than checking first: a check-then-insert has a race
    window (two requests both see "no such name"), while the constraint is atomic."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise LabelExistsError("A label with that name already exists on this board")


def delete_label(db: Session, label: Label) -> None:
    """The database removes it from every card (ON DELETE CASCADE on card_labels)."""
    db.delete(label)
    db.commit()


# ── On cards: PUT/DELETE semantics, so both are idempotent ──


def attach(db: Session, card: Card, label_id: int) -> None:
    label = db.get(Label, label_id)
    # The composite foreign key would reject a label from another board too, but checking here
    # gives a clear error instead of a generic IntegrityError.
    if label is None or label.board_id != card.board_id:
        raise LabelNotOnBoardError("label_id is not a label on this card's board")
    if db.get(CardLabel, (card.id, label_id)) is None:
        db.add(CardLabel(card_id=card.id, label_id=label_id, board_id=card.board_id))
        db.commit()


def detach(db: Session, card: Card, label_id: int) -> None:
    link = db.get(CardLabel, (card.id, label_id))
    if link is not None:
        db.delete(link)
        db.commit()


def labels_for_board(db: Session, board_id: int) -> list[Label]:
    return list(db.scalars(select(Label).where(Label.board_id == board_id).order_by(Label.name)))
