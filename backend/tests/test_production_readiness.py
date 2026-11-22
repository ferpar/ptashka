"""Settings checks and the health endpoint: what a deploy relies on."""

import pytest
from sqlalchemy.exc import OperationalError

from ptashka.config import DEV_JWT_SECRET, ConfigurationError, validate_settings


def test_development_accepts_the_default_secret():
    validate_settings("development", DEV_JWT_SECRET)


@pytest.mark.parametrize("secret", [DEV_JWT_SECRET, "short", "x" * 31])
def test_production_refuses_weak_secrets(secret):
    with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY"):
        validate_settings("production", secret)


def test_production_accepts_a_strong_secret():
    validate_settings("production", "k" * 48)


def test_production_refuses_test_strength_password_hashing():
    with pytest.raises(ConfigurationError, match="BCRYPT_ROUNDS"):
        validate_settings("production", "k" * 48, bcrypt_rounds=4)
    validate_settings("development", DEV_JWT_SECRET, bcrypt_rounds=4)  # Fine outside production.


def test_the_suite_really_uses_cheap_hashing():
    """Guards the speed-up: if this setting stops applying, the suite silently gets 11x slower."""
    from ptashka.auth.password import hash_password

    assert hash_password("password123").startswith("$2b$04$")  # $2b$<cost>$...


def test_health_checks_the_database(client):
    assert client.get("/health").json() == {"status": "healthy", "database": "ok"}


def test_health_is_503_when_the_database_is_unreachable(client, db_session, monkeypatch):
    def down(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(db_session, "execute", down)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"
