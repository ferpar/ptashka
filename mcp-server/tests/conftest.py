"""Tests drive the MCP server against the *real* ptashka backend, in-process:

    MCP Client → MCP server tools → httpx (ASGITransport, no network) → FastAPI app → SQLite

So every test goes through the real API, permissions and database rules, not a fake that could
drift from them. Requires the backend installed in this environment: `uv pip install -e ../backend`.
"""

from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
import pytest
from mcp import Client
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ptashka.auth.password import hash_password
from ptashka.db.database import get_db, unit_of_work
from ptashka.main import app
from ptashka.models.db import Base, TokenScope, User, UserStatus
from ptashka.services import activity_service, token_service
from ptashka_mcp.api import PtashkaApi
from ptashka_mcp.server import build_server

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _configure(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
    dbapi_connection.isolation_level = None  # SQLAlchemy's pysqlite savepoint recipe (see backend conftest).


@event.listens_for(engine, "begin")
def _begin(conn) -> None:  # type: ignore[no-untyped-def]
    conn.exec_driver_sql("BEGIN")


@pytest.fixture
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()

    def override() -> Generator[Session, None, None]:
        yield from unit_of_work(session)

    app.dependency_overrides[get_db] = override
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity_service, "SETTLE", timedelta(0))


def make_user(db: Session, name: str) -> User:
    user = User(email=f"{name.lower()}@example.com", hashed_password=hash_password("password123"),
                display_name=name, status=UserStatus.ACTIVE)
    db.add(user)
    db.commit()
    return user


def token_for(db: Session, user: User, scope: TokenScope = TokenScope.WRITE) -> str:
    _, raw = token_service.create_token(db, user, "test agent", scope)
    db.commit()
    return raw


@asynccontextmanager
async def connect(token: str, read_only: bool = False) -> AsyncIterator[Client]:
    api = PtashkaApi("http://ptashka.test", token, transport=httpx.ASGITransport(app=app))
    async with Client(build_server(api, read_only=read_only)) as client:
        yield client
    await api.aclose()
