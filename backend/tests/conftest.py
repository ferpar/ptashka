"""Pytest fixtures.

By default tests run against an in-memory SQLite database: fast, nothing to start.
Set TEST_POSTGRES_URL to run the *whole* suite against real Postgres instead (what
production uses, and what CI should use). Its tables are dropped, so point it at a
throwaway database:

    docker exec ptashka-db-1 createdb -U ptashka ptashka_test   # once
    TEST_POSTGRES_URL=postgresql://ptashka:ptashka@localhost:5435/ptashka_test .venv/bin/pytest

Either way every test gets fresh tables, and the app's `get_db` is swapped for one that
hands out the test session wrapped in the real unit of work (commit on success,
rollback on error), so transactions behave as in production.
"""

import os

# Before any ptashka import: password hashing reads it at import time (see auth/password.py).
os.environ.setdefault("BCRYPT_ROUNDS", "4")

from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ptashka.auth.jwt import create_access_token
from ptashka.auth.password import hash_password
from ptashka.db.database import get_db, normalize_database_url, unit_of_work
from ptashka.main import app
from ptashka.models.db import Base, User, UserRole, UserStatus

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


def _make_engine() -> Engine:
    if TEST_POSTGRES_URL:
        return create_engine(normalize_database_url(TEST_POSTGRES_URL))

    # StaticPool: every connection is the *same* connection, otherwise each new
    # connection to ":memory:" would see its own empty database.
    sqlite = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(sqlite, "connect")
    def _configure(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        # SQLite ignores foreign keys (and so ON DELETE CASCADE / SET NULL) unless asked.
        # Postgres always enforces them; turn them on so tests behave like production.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        # Python's sqlite3 driver manages transactions itself: it delays BEGIN until the first
        # INSERT/UPDATE/DELETE, and a SAVEPOINT doesn't count. A savepoint opened outside a
        # transaction *becomes* the transaction, so releasing it commits everything, and a later
        # rollback can't undo it. Switch the driver's handling off...
        dbapi_connection.isolation_level = None

    @event.listens_for(sqlite, "begin")
    def _begin(conn) -> None:  # type: ignore[no-untyped-def]
        # ...and let SQLAlchemy start transactions explicitly, as it does on Postgres.
        # (The recipe from SQLAlchemy's docs, "Serializable isolation / Savepoints / Transactional DDL".)
        conn.exec_driver_sql("BEGIN")

    return sqlite


engine = _make_engine()
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    Base.metadata.drop_all(bind=engine)  # In case a previous run was interrupted (Postgres persists).
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        # The real unit of work around the shared test session: each request commits or rolls back.
        yield from unit_of_work(db_session)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


TRANSACTION_CONTROL = {"BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE"}


@pytest.fixture
def count_queries() -> Generator[list[str], None, None]:
    """Records every SQL statement sent to the database while the test runs.

    Usage: `count_queries.clear()`, do something, then `len(count_queries)`.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:  # type: ignore[no-untyped-def]
        # Data queries only: BEGIN / SAVEPOINT / RELEASE are transaction control, and whether a
        # BEGIN falls inside the measured window depends on what ran before, not on board size.
        if statement.split(None, 1)[0].upper() not in TRANSACTION_CONTROL:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    yield statements
    event.remove(engine, "before_cursor_execute", record)


@pytest.fixture
def make_user(db_session: Session) -> Callable[..., User]:
    """Factory fixture: call it to create as many users as a test needs."""

    def factory(
        email: str = "user@example.com",
        role: UserRole = UserRole.USER,
        status: UserStatus = UserStatus.ACTIVE,
        password: str = "password123",
    ) -> User:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            display_name=email.split("@")[0],
            role=role,
            status=status,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return factory


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user()


@pytest.fixture
def admin(make_user: Callable[..., User]) -> User:
    return make_user(email="admin@example.com", role=UserRole.ADMIN)
