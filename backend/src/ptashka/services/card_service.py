"""Cards: create, update, move within/between lists of a board."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ptashka.models.db import ActivityKind, BoardList, BoardMember, Card, CardAssignee, ChecklistItem, Comment, User
from ptashka.services import activity_service, locks, ordering
from ptashka.services.board_service import InvalidMoveError, toggled_timestamp


class NotAMemberError(Exception):
    pass


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
    actor: User,
    board_list: BoardList,
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
        created_by_id=actor.id,
    )
    db.add(card)
    db.flush()
    db.refresh(card)
    activity_service.record(
        db, actor, ActivityKind.CARD_CREATED, card.board_id, card, list_id=board_list.id, list_name=board_list.name
    )
    return card


def _record_flag(db: Session, actor: User, card: Card, was_on: bool, now_on: bool, on: ActivityKind, off: ActivityKind) -> None:
    """Record completed/reopened, archived/restored... only when the flag actually flipped."""
    if was_on != now_on:
        activity_service.record(db, actor, on if now_on else off, card.board_id, card)


EDITABLE = ("title", "description", "due_at")


def update_card(db: Session, actor: User, card: Card, changes: dict[str, Any]) -> Card:
    """Apply a PATCH. `changes` holds only the fields the client sent (see schemas.CardUpdateRequest).

    If `version` is sent, the update only applies when the card is still at that version:
    the client is saying "these edits are based on version N".
    """
    expected = changes.pop("version", None)
    if expected is not None and expected != card.version:
        # Check 1 (cheap, gives a clear error): the client's copy is already outdated.
        raise VersionConflictError(card.version)

    before = {field: getattr(card, field) for field in EDITABLE}
    was_completed, was_archived = card.completed_at is not None, card.archived_at is not None
    try:
        # A savepoint: changes made inside are flushed when the block ends. If that flush fails,
        # only the savepoint is rolled back; the request's transaction stays usable, and the
        # decision to commit or roll back the whole request stays with the unit of work.
        with db.begin_nested():
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
    except StaleDataError:
        # Check 2 (the race): another request committed between our read and our write.
        # The UPDATE ... WHERE version = N matched no row, so nothing was overwritten.
        db.refresh(card)
        raise VersionConflictError(card.version)

    # Recorded only after the update succeeded: a refused update leaves no trace.
    if diff := activity_service.changes(before, {field: getattr(card, field) for field in EDITABLE}):
        activity_service.record(db, actor, ActivityKind.CARD_UPDATED, card.board_id, card, **diff)
    _record_flag(db, actor, card, was_completed, card.completed_at is not None, ActivityKind.CARD_COMPLETED, ActivityKind.CARD_REOPENED)
    _record_flag(db, actor, card, was_archived, card.archived_at is not None, ActivityKind.CARD_ARCHIVED, ActivityKind.CARD_RESTORED)
    db.refresh(card)
    return card


def move_card(db: Session, actor: User, card: Card, list_id: int, after_id: int | None) -> Card:
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
    was_completed = card.completed_at is not None
    if target.id != source.id:
        activity_service.record(
            db, actor, ActivityKind.CARD_MOVED, card.board_id, card,
            from_list_id=source.id, from_list=source.name, to_list_id=target.id, to_list=target.name,
        )
        if target.is_done or source.is_done:
            card.completed_at = toggled_timestamp(card.completed_at, target.is_done)
            _record_flag(db, actor, card, was_completed, target.is_done, ActivityKind.CARD_COMPLETED, ActivityKind.CARD_REOPENED)
    # Assigning the relationship (not just list_id) lets SQLAlchemy copy *both* columns of the
    # composite key from the target list and keep source.cards / target.cards in sync in memory.
    card.board_list = target
    card.position = ordering.place(siblings, index)
    db.flush()
    db.refresh(card)
    return card


def delete_card(db: Session, actor: User, card: Card) -> None:
    # No `card=`: the row is about to disappear, so the entry keeps only its title.
    activity_service.record(db, actor, ActivityKind.CARD_DELETED, card.board_id, card_title=card.title)
    db.delete(card)
    db.flush()


# ── Assignees: PUT/DELETE semantics, so both are idempotent ──


def assign(db: Session, actor: User, card: Card, user_id: int) -> None:
    # Like labels: the composite foreign key to board_members is the real guarantee; this check
    # turns its IntegrityError into a clear message.
    member = db.get(BoardMember, (card.board_id, user_id))
    if member is None:
        raise NotAMemberError("Only members of the board can be assigned")
    if db.get(CardAssignee, (card.id, user_id)) is None:  # Already assigned: nothing happens, nothing is recorded.
        db.add(CardAssignee(card_id=card.id, user_id=user_id, board_id=card.board_id))
        activity_service.record(
            db, actor, ActivityKind.ASSIGNEE_ADDED, card.board_id, card, user_id=user_id, user_name=member.user.display_name
        )
        db.flush()


def unassign(db: Session, actor: User, card: Card, user_id: int) -> None:
    link = db.get(CardAssignee, (card.id, user_id))
    if link is not None:
        member = db.get(BoardMember, (card.board_id, user_id))
        db.delete(link)
        activity_service.record(
            db, actor, ActivityKind.ASSIGNEE_REMOVED, card.board_id, card,
            user_id=user_id, user_name=member.user.display_name if member else None,
        )
        db.flush()


# ── Counts shown on cards ──


@dataclass
class CardStats:
    checklist_done: int = 0
    checklist_total: int = 0
    comment_count: int = 0


def _stats(db: Session, which_cards: ColumnElement[bool]) -> defaultdict[int, CardStats]:
    """Checklist and comment counts for many cards in two queries, with the counting done by the
    database (GROUP BY) instead of loading every item and comment into Python.

    COUNT(done_at) counts non-null values only, i.e. the done items.
    """
    stats: defaultdict[int, CardStats] = defaultdict(CardStats)
    checklist = (
        select(ChecklistItem.card_id, func.count(), func.count(ChecklistItem.done_at))
        .join(Card, Card.id == ChecklistItem.card_id)
        .where(which_cards)
        .group_by(ChecklistItem.card_id)
    )
    for card_id, total, done in db.execute(checklist):
        stats[card_id].checklist_total = total
        stats[card_id].checklist_done = done
    comments = (
        select(Comment.card_id, func.count())
        .join(Card, Card.id == Comment.card_id)
        .where(which_cards)
        .group_by(Comment.card_id)
    )
    for card_id, count in db.execute(comments):
        stats[card_id].comment_count = count
    return stats  # A defaultdict: cards with no items/comments get CardStats() (all zeros).


def stats_for_board(db: Session, board_id: int) -> defaultdict[int, CardStats]:
    # Card.board_id (denormalized in phase 3) makes this a simple filter, not a join through lists.
    return _stats(db, Card.board_id == board_id)


def stats_for_cards(db: Session, card_ids: list[int]) -> defaultdict[int, CardStats]:
    return _stats(db, Card.id.in_(card_ids))


def stats_for_card(db: Session, card_id: int) -> CardStats:
    return _stats(db, Card.id == card_id)[card_id]
