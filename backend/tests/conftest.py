"""Pytest fixtures.

Tests run against an in-memory SQLite database: every test gets fresh tables,
and the app's `get_db` dependency is swapped for one that hands out the test
session. No Postgres needed to run the suite.
"""

from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ptashka.auth.jwt import create_access_token
from ptashka.auth.password import hash_password
from ptashka.db.database import get_db
from ptashka.main import app
from ptashka.models.db import Base, User, UserRole, UserStatus

# StaticPool: every connection is the *same* connection, otherwise each new
# connection to ":memory:" would see its own empty database.
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
