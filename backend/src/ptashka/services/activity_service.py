"""The activity log: recording what happened, and reading it back.

Services call `record(...)` right where a change happens. Nothing here commits: the entry joins the
request's transaction, so a change and its record are saved together or not at all.

Two ways to read it:
- `board_page` / `card_page`: newest first, paging backwards with `before` (a history view).
- `feed`: oldest first, entries after `since`, across all your boards ("what changed since I last
  looked?", the question agents ask when polling).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session, joinedload

from ptashka.models.db import Activity, ActivityKind, BoardMember, Card, User

# How long an entry must have existed before the `since` feed returns it. Ids come from a sequence
# and are handed out at INSERT time, but transactions *commit* in any order: entry 101 may become
# visible after entry 102. A poller that already moved past 102 would then never see 101. Waiting
# until entries are a few seconds old (far longer than any of our transactions) lets late commits
# land first. Tests set this to 0, except the one that checks it.
SETTLE = timedelta(seconds=5)


def record(db: Session, actor: User, kind: ActivityKind, board_id: int, card: Card | None = None, **data: Any) -> None:
    """Append an entry. `card`'s title is stored with it, so the entry reads well even if the card
    is renamed or deleted later. (For a deleted card, pass `card_title=...` and no `card`: the row
    is about to disappear and can't be referenced.)"""
    if card is not None:
        data = {"card_title": card.title, **data}
    db.add(Activity(board_id=board_id, card_id=card.id if card else None, actor_id=actor.id, kind=kind, data=data))


def changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any] | None:
    """The `data` for an "updated" entry: which fields changed, and old → new for the short ones.
    None when nothing actually changed (no entry should be recorded)."""
    changed = sorted(k for k in after if after[k] != before.get(k))
    if not changed:
        return None
    short = [k for k in changed if k != "description"]  # Long text: just note that it changed.
    return {
        "changed": changed,
        "from": {k: _jsonable(before.get(k)) for k in short},
        "to": {k: _jsonable(after[k]) for k in short},
    }


def _jsonable(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


# ── Reading ──


def _page(db: Session, where: ColumnElement[bool], limit: int, before: int | None) -> list[Activity]:
    stmt = select(Activity).where(where).options(joinedload(Activity.actor)).order_by(Activity.id.desc()).limit(limit)
    if before is not None:
        stmt = stmt.where(Activity.id < before)
    return list(db.scalars(stmt))


def board_page(db: Session, board_id: int, limit: int, before: int | None) -> list[Activity]:
    return _page(db, Activity.board_id == board_id, limit, before)


def card_page(db: Session, card_id: int, limit: int, before: int | None) -> list[Activity]:
    return _page(db, Activity.card_id == card_id, limit, before)


def feed(db: Session, user: User, since: int, limit: int) -> list[Activity]:
    """Entries after `since`, oldest first, from every board `user` is a member of.
    Only *settled* entries (see SETTLE), so following `since` never skips one."""
    my_boards = select(BoardMember.board_id).where(BoardMember.user_id == user.id)
    stmt = (
        select(Activity)
        .where(
            Activity.board_id.in_(my_boards),
            Activity.id > since,
            Activity.created_at <= datetime.now(timezone.utc) - SETTLE,
        )
        .options(joinedload(Activity.actor))
        .order_by(Activity.id)
        .limit(limit)
    )
    return list(db.scalars(stmt))
