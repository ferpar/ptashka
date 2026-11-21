"""Pessimistic row locks for operations that read siblings and then write based on them.

The race: two requests read a list's card positions at the same time, both compute
the same midpoint (or one renumbers while the other computes from stale numbers).
The fix is to make writers to the *same parent* take turns: each one locks the parent
row (the board for lists, the list for cards, the card for checklist items) with SELECT ... FOR UPDATE before reading
siblings. A second request blocks on that SELECT until the first one commits, then reads
the updated positions.

Rules that keep this deadlock-free:
- Each operation locks exactly one parent row, so two requests can't each hold a lock
  the other is waiting for.
- Lock *first*, then read whatever the decision depends on.

SQLite has no row locks (its writes lock the whole database), so SQLAlchemy simply omits
FOR UPDATE there; tests/test_concurrency.py checks this against real Postgres.
"""

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.models.db import Board, BoardList, Card

Parent = TypeVar("Parent", Board, BoardList, Card)


def lock(db: Session, model: type[Parent], id_: int) -> Parent:
    """SELECT ... FOR UPDATE the row, held until the transaction commits or rolls back.

    populate_existing: if the object is already in the session (the permission check loaded
    it), overwrite its attributes with what we read *after* acquiring the lock, which may
    be newer (e.g. the list was archived meanwhile).
    """
    stmt = select(model).where(model.id == id_).with_for_update().execution_options(populate_existing=True)
    return db.scalars(stmt).one()
