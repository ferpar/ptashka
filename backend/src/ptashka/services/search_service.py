"""Cross-board card search: "my open cards everywhere, due this week, labelled urgent".

A query object: the filters arrive as one value (`CardFilters`), and each one that's set adds its
own WHERE clause to the statement. SQLAlchemy statements are immutable values, so building one up
step by step (`stmt = stmt.where(...)`) is safe and reads like the list of filters it implements.

Results are always limited to boards the user is a member of: that join is the permission check,
so a search can never surface a card the user couldn't open.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ptashka.models.db import Board, BoardList, BoardMember, Card, CardAssignee, CardLabel, Label


@dataclass(frozen=True)
class CardFilters:
    assignee_id: int | None = None
    board_id: int | None = None
    label: str | None = None  # A label *name*: boards have their own labels, names are what they share.
    due_before: datetime | None = None
    due_after: datetime | None = None
    overdue: bool = False  # Due in the past and not completed.
    completed: bool | None = None  # None: both.
    include_archived: bool = False  # Archived cards, and cards on archived lists or boards.
    text: str | None = None  # In title or description, case-insensitive.


@dataclass
class SearchHit:
    card: Card
    board_name: str
    list_name: str


def _like_pattern(text: str) -> str:
    """`%` and `_` are wildcards in LIKE. Escape them, so searching "100%" finds "100%", not "100"
    followed by anything. (Not a SQL injection risk either way: values are always sent as bound
    parameters. This is about meaning, not safety.)"""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _apply(stmt: Select[Card, str, str], f: CardFilters) -> Select[Card, str, str]:
    if f.board_id is not None:
        stmt = stmt.where(Card.board_id == f.board_id)
    if f.assignee_id is not None:
        # EXISTS rather than a JOIN: a JOIN to a link table could return a card once per match.
        stmt = stmt.where(
            select(CardAssignee).where(CardAssignee.card_id == Card.id, CardAssignee.user_id == f.assignee_id).exists()
        )
    if f.label is not None:
        stmt = stmt.where(
            select(CardLabel)
            .join(Label, Label.id == CardLabel.label_id)
            .where(CardLabel.card_id == Card.id, func.lower(Label.name) == f.label.strip().lower())
            .exists()
        )
    if f.due_before is not None:
        stmt = stmt.where(Card.due_at < f.due_before)
    if f.due_after is not None:
        stmt = stmt.where(Card.due_at >= f.due_after)
    if f.overdue:
        stmt = stmt.where(Card.due_at < datetime.now(timezone.utc), Card.completed_at.is_(None))
    if f.completed is not None:
        stmt = stmt.where(Card.completed_at.is_not(None) if f.completed else Card.completed_at.is_(None))
    if not f.include_archived:
        stmt = stmt.where(Card.archived_at.is_(None), BoardList.archived_at.is_(None), Board.archived_at.is_(None))
    if f.text:
        pattern = _like_pattern(f.text.strip())
        stmt = stmt.where(or_(Card.title.ilike(pattern, escape="\\"), Card.description.ilike(pattern, escape="\\")))
    return stmt


def search_cards(db: Session, user_id: int, filters: CardFilters, limit: int, offset: int) -> list[SearchHit]:
    stmt = (
        select(Card, Board.name, BoardList.name)
        .join(BoardMember, (BoardMember.board_id == Card.board_id) & (BoardMember.user_id == user_id))
        .join(Board, Board.id == Card.board_id)
        .join(BoardList, BoardList.id == Card.list_id)
        .options(selectinload(Card.label_links), selectinload(Card.assignee_links))
        # Soonest due first, undated last; id keeps the order stable between pages.
        .order_by(Card.due_at.asc().nulls_last(), Card.id)
        .limit(limit)
        .offset(offset)
    )
    return [SearchHit(card, board_name, list_name) for card, board_name, list_name in db.execute(_apply(stmt, filters))]
