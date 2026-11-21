"""Cards: create, update, move within/between lists of a board."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ptashka.models.db import BoardList, Card, User
from ptashka.services import locks, ordering
from ptashka.services.board_service import InvalidMoveError, toggled_timestamp


class VersionConflictError(Exception):
    """The card changed since the client loaded it (optimistic locking)."""

    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__(f"Card was modified by someone else (now at version {current_version})")


def _ordered_cards(db: Session, list_id: int, exclude_id: int | None = None) -> list[Card]:
    # Archived cards are included so they reappear in their old slot when restored.
    stmt = select(Card).where(Card.list_id == list_id).order_by(Card.position, Card.id)
    if exclude_id is not None:
        stmt = stmt.where(Card.id != exclude_id)
    return list(db.scalars(stmt))


def create_card(
    db: Session,
    board_list: BoardList,
    creator: User,
    title: str,
    description: str | None = None,
    due_at: datetime | None = None,
) -> Card:
    """New cards go at the bottom of their list. A card created in the done list starts completed."""
    board_list = locks.lock(db, BoardList, board_list.id)
    if board_list.archived_at is not None:
        raise InvalidMoveError("Can't add cards to an archived list")
    siblings = _ordered_cards(db, board_list.id)
    card = Card(
        list_id=board_list.id,
        board_id=board_list.board_id,
        title=title.strip(),
        description=description,
        due_at=due_at,
        position=ordering.place(siblings, len(siblings)),
        completed_at=toggled_timestamp(None, board_list.is_done),
        created_by_id=creator.id,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def update_card(db: Session, card: Card, changes: dict[str, Any]) -> Card:
    """Apply a PATCH. `changes` holds only the fields the client sent (see schemas.CardUpdateRequest).

    If `version` is sent, the update only applies when the card is still at that version:
    the client is saying "these edits are based on version N".
    """
    expected = changes.pop("version", None)
    if expected is not None and expected != card.version:
        # Check 1 (cheap, gives a clear error): the client's copy is already outdated.
        raise VersionConflictError(card.version)

    if changes.get("title") is not None:
        card.title = changes["title"].strip()
    # These can be cleared with null.
    if "description" in changes:
        card.description = changes["description"]
    if "due_at" in changes:
        card.due_at = changes["due_at"]
    # Booleans in the API, timestamps in the database.
    if changes.get("completed") is not None:
        card.completed_at = toggled_timestamp(card.completed_at, changes["completed"])
    if changes.get("archived") is not None:
        card.archived_at = toggled_timestamp(card.archived_at, changes["archived"])
    try:
        db.commit()
    except StaleDataError:
        # Check 2 (the race): another request committed between our read and our write.
        # The UPDATE ... WHERE version = N matched no row, so nothing was overwritten.
        db.rollback()
        db.refresh(card)
        raise VersionConflictError(card.version)
    db.refresh(card)
    return card


def move_card(db: Session, card: Card, list_id: int, after_id: int | None) -> Card:
    """Put `card` into list `list_id`, right after card `after_id` (None = top of the list).

    Moving into the board's done list completes the card; moving out of it reopens the card.
    """
    if after_id == card.id:
        raise InvalidMoveError("A card can't be placed after itself")
    target = db.get(BoardList, list_id)
    # A list on another board is treated like a missing one: moving between boards would change
    # who can see the card, so it isn't a plain move.
    if target is None or target.board_id != card.board_id:
        raise InvalidMoveError("list_id is not a list on this board")
    target = locks.lock(db, BoardList, target.id)  # Re-read after locking: it may have changed meanwhile.
    if target.archived_at is not None:
        raise InvalidMoveError("Can't move a card into an archived list")

    siblings = _ordered_cards(db, target.id, exclude_id=card.id)
    try:
        index = ordering.index_after([s.id for s in siblings], after_id)
    except ValueError:
        raise InvalidMoveError("after_id is not a card in the target list")

    source = card.board_list
    if target.id != source.id and (target.is_done or source.is_done):
        card.completed_at = toggled_timestamp(card.completed_at, target.is_done)
    # Assigning the relationship (not just list_id) lets SQLAlchemy copy *both* columns of the
    # composite key from the target list and keep source.cards / target.cards in sync in memory.
    card.board_list = target
    card.position = ordering.place(siblings, index)
    db.commit()
    db.refresh(card)
    return card


def delete_card(db: Session, card: Card) -> None:
    db.delete(card)
    db.commit()
