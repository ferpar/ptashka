"""Database connection and session management."""

import os
from collections.abc import Generator

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


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed afterwards.

    Everything before `yield` runs before the endpoint; everything after runs
    once the response is sent (even if the endpoint raised).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
