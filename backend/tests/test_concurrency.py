"""Concurrency tests that need real Postgres: SQLite has no row locks, so FOR UPDATE is a no-op there.

Skipped unless TEST_POSTGRES_URL is set (see conftest.py); `-m postgres` runs only these.
"""

import os
import threading
import time
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ptashka.db.database import normalize_database_url
from ptashka.models.db import Base, BoardList, Card, User, UserStatus
from ptashka.services import board_service, card_service, ordering

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not TEST_POSTGRES_URL, reason="set TEST_POSTGRES_URL to run Postgres concurrency tests"),
]


@pytest.fixture
def pg_session_factory() -> Generator[sessionmaker[Session], None, None]:
    assert TEST_POSTGRES_URL
    engine = create_engine(normalize_database_url(TEST_POSTGRES_URL))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_concurrent_moves_into_the_same_gap_get_distinct_positions(pg_session_factory, monkeypatch):
    """Two requests move different cards right after card A at the same moment.

    Without the list lock, both read positions [A=1024, B=2048], both compute 1536, and the cards tie.
    With it, the second request waits, then sees the first card already there and picks another slot.
    """
    # Services don't commit: `factory.begin()` is the unit of work here, committing when the block ends.
    with pg_session_factory.begin() as db:
        user = User(email="u@example.com", hashed_password="x", display_name="u", status=UserStatus.ACTIVE)
        db.add(user)
        db.flush()
        board = board_service.create_board(db, user, "Race", None, default_lists=True)
        todo, doing = board.lists[0], board.lists[1]
        a = card_service.create_card(db, todo, user, "A")
        card_service.create_card(db, todo, user, "B")
        movers = [card_service.create_card(db, doing, user, name).id for name in ("C", "D")]
        todo_id, a_id = todo.id, a.id

    # Widen the race window: pause between reading the siblings and writing the new position.
    real_place = ordering.place

    def slow_place(siblings, index):  # type: ignore[no-untyped-def]
        time.sleep(0.3)
        return real_place(siblings, index)

    monkeypatch.setattr(ordering, "place", slow_place)

    start = threading.Barrier(len(movers))
    errors: list[BaseException] = []

    def move(card_id: int) -> None:
        try:
            with pg_session_factory.begin() as db:  # Each "request": own session, connection, transaction.
                card = db.get(Card, card_id)
                assert card is not None
                start.wait()  # Both threads call move_card at the same moment.
                card_service.move_card(db, card, todo_id, after_id=a_id)
        except BaseException as e:  # Surface thread failures in the test.
            errors.append(e)

    threads = [threading.Thread(target=move, args=(card_id,)) for card_id in movers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, errors

    with pg_session_factory() as db:
        cards = db.scalars(select(Card).where(Card.list_id == todo_id).order_by(Card.position)).all()
        positions = [c.position for c in cards]
        assert len(set(positions)) == len(positions), f"tied positions: {positions}"
        assert cards[0].title == "A" and cards[-1].title == "B"
        assert {c.title for c in cards[1:3]} == {"C", "D"}


def test_lists_are_locked_too(pg_session_factory):
    """Sanity check that the lock is real: a second transaction can't lock the same list until the first ends."""
    with pg_session_factory.begin() as db:
        user = User(email="u@example.com", hashed_password="x", display_name="u", status=UserStatus.ACTIVE)
        db.add(user)
        db.flush()
        list_id = board_service.create_board(db, user, "Lock", None, default_lists=True).lists[0].id

    from ptashka.services import locks

    first = pg_session_factory()
    second = pg_session_factory()
    try:
        locks.lock(first, BoardList, list_id)
        # NOWAIT: fail immediately instead of blocking if the row is locked.
        from sqlalchemy.exc import OperationalError

        with pytest.raises(OperationalError, match="could not obtain lock"):
            second.scalars(select(BoardList).where(BoardList.id == list_id).with_for_update(nowait=True)).one()
        second.rollback()
        first.commit()  # Releases the lock...
        second.scalars(select(BoardList).where(BoardList.id == list_id).with_for_update(nowait=True)).one()  # ...so now it works.
    finally:
        first.close()
        second.close()
