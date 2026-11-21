"""Board labels, and attaching them to cards."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ptashka.models.db import ActivityKind, Board, Card, CardLabel, Label, LabelColor, User
from ptashka.services import activity_service


class LabelExistsError(Exception):
    pass


class LabelNotOnBoardError(Exception):
    pass


def create_label(db: Session, board: Board, name: str, color: LabelColor) -> Label:
    label = Label(board_id=board.id, name=name.strip(), color=color)
    with _unique_name():
        with db.begin_nested():
            db.add(label)
    db.refresh(label)
    return label


def update_label(db: Session, label: Label, changes: dict[str, Any]) -> Label:
    with _unique_name():
        with db.begin_nested():
            if changes.get("name") is not None:
                label.name = changes["name"].strip()
            if changes.get("color") is not None:
                label.color = changes["color"]
    db.refresh(label)
    return label


@contextmanager
def _unique_name() -> Iterator[None]:
    """Let the unique constraint decide, rather than checking first: a check-then-insert has a race
    window (two requests both see "no such name"), while the constraint is atomic.

    The callers make their change inside a savepoint (`begin_nested`), so a violation rolls back
    just that change and the request can still answer with a clean 409.
    """
    try:
        yield
    except IntegrityError:
        raise LabelExistsError("A label with that name already exists on this board")


def delete_label(db: Session, label: Label) -> None:
    """The database removes it from every card (ON DELETE CASCADE on card_labels)."""
    db.delete(label)
    db.flush()


# ── On cards: PUT/DELETE semantics, so both are idempotent ──


def attach(db: Session, actor: User, card: Card, label_id: int) -> None:
    label = db.get(Label, label_id)
    # The composite foreign key would reject a label from another board too, but checking here
    # gives a clear error instead of a generic IntegrityError.
    if label is None or label.board_id != card.board_id:
        raise LabelNotOnBoardError("label_id is not a label on this card's board")
    if db.get(CardLabel, (card.id, label_id)) is None:  # Already there: nothing happens, nothing is recorded.
        db.add(CardLabel(card_id=card.id, label_id=label_id, board_id=card.board_id))
        activity_service.record(db, actor, ActivityKind.LABEL_ADDED, card.board_id, card, label_id=label.id, label_name=label.name)
        db.flush()


def detach(db: Session, actor: User, card: Card, label_id: int) -> None:
    link = db.get(CardLabel, (card.id, label_id))
    if link is not None:
        label = db.get(Label, label_id)
        db.delete(link)
        activity_service.record(
            db, actor, ActivityKind.LABEL_REMOVED, card.board_id, card, label_id=label_id, label_name=label.name if label else None
        )
        db.flush()


def labels_for_board(db: Session, board_id: int) -> list[Label]:
    return list(db.scalars(select(Label).where(Label.board_id == board_id).order_by(Label.name)))
