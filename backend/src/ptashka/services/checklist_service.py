"""Checklist items: ordered sub-tasks of a card."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.models.db import Card, ChecklistItem
from ptashka.services import locks, ordering
from ptashka.services.board_service import InvalidMoveError, toggled_timestamp


def _ordered_items(db: Session, card_id: int, exclude_id: int | None = None) -> list[ChecklistItem]:
    stmt = select(ChecklistItem).where(ChecklistItem.card_id == card_id).order_by(ChecklistItem.position, ChecklistItem.id)
    if exclude_id is not None:
        stmt = stmt.where(ChecklistItem.id != exclude_id)
    return list(db.scalars(stmt))


def add_item(db: Session, card: Card, text: str) -> ChecklistItem:
    """New items go at the end."""
    locks.lock(db, Card, card.id)
    siblings = _ordered_items(db, card.id)
    item = ChecklistItem(card_id=card.id, text=text.strip(), position=ordering.place(siblings, len(siblings)))
    db.add(item)
    db.flush()
    db.refresh(item)
    return item


def update_item(db: Session, item: ChecklistItem, changes: dict[str, Any]) -> ChecklistItem:
    if changes.get("text") is not None:
        item.text = changes["text"].strip()
    if changes.get("done") is not None:
        item.done_at = toggled_timestamp(item.done_at, changes["done"])
    db.flush()
    db.refresh(item)
    return item


def move_item(db: Session, item: ChecklistItem, after_id: int | None) -> ChecklistItem:
    """Reorder within the same card: right after item `after_id`, or first when None."""
    if after_id == item.id:
        raise InvalidMoveError("An item can't be placed after itself")
    locks.lock(db, Card, item.card_id)
    siblings = _ordered_items(db, item.card_id, exclude_id=item.id)
    try:
        index = ordering.index_after([s.id for s in siblings], after_id)
    except ValueError:
        raise InvalidMoveError("after_id is not an item on this card's checklist")
    item.position = ordering.place(siblings, index)
    db.flush()
    db.refresh(item)
    return item


def delete_item(db: Session, item: ChecklistItem) -> None:
    db.delete(item)
    db.flush()
