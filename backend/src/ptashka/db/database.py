"""Database connection and session management."""

import os
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(url: str) -> str:
    """Accept the URL forms hosting tools hand out.

    Coolify, Heroku and others emit `postgres://`, which SQLAlchemy rejects;
    a bare `postgresql://` would pick the driver by SQLAlchemy's default, so
    pin psycopg 3 (the driver we install) explicitly.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "postgresql://ptashka:ptashka@localhost:5435/ptashka")
)

# pool_pre_ping does a tiny `SELECT 1` before reusing a pooled connection, so a
# database restart surfaces as a reconnect rather than an OperationalError.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def unit_of_work(session: Session) -> Generator[Session, None, None]:
    """One business operation = one transaction: commit if everything succeeded, roll back otherwise.

    Services never commit; they only flush (send SQL, get ids, surface constraint errors). The
    caller that defines the operation (here: an HTTP request) decides when it's complete. So
    "move the card" and "record that it moved" (phase 5) land together or not at all.
    """
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session and one transaction per request (see unit_of_work)."""
    with SessionLocal() as session:
        yield from unit_of_work(session)


# Use this in every endpoint and dependency: `db: DbSession`.
#
# scope="function" makes FastAPI run the code after `yield` (the COMMIT) *before* sending the
# response. With the default scope it runs *after*: a failed commit would reach the client as
# a 200, i.e. "saved" when nothing was. Declaring it once also guarantees every Depends in a
# request shares the same cached session.
DbSession = Annotated[Session, Depends(get_db, scope="function")]
