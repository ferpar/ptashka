"""Startup checks for settings that must never be left at a development default in production.

Fail fast: a misconfigured server should refuse to start, loudly, rather than run in an unsafe state
that nobody notices (e.g. signing login tokens with a secret that's printed in the source code).
"""

import os

DEV_JWT_SECRET = "dev-secret-key-change-in-production"
MIN_SECRET_LENGTH = 32
MIN_BCRYPT_ROUNDS = 12

ENVIRONMENT = os.getenv("PTASHKA_ENV", "development")


class ConfigurationError(RuntimeError):
    pass


def validate_settings(environment: str, jwt_secret: str, bcrypt_rounds: int = MIN_BCRYPT_ROUNDS) -> None:
    if environment != "production":
        return
    if bcrypt_rounds < MIN_BCRYPT_ROUNDS:
        raise ConfigurationError(
            f"BCRYPT_ROUNDS={bcrypt_rounds} is for tests only; production needs at least {MIN_BCRYPT_ROUNDS} (or leave it unset)"
        )
    if jwt_secret == DEV_JWT_SECRET or len(jwt_secret) < MIN_SECRET_LENGTH:
        raise ConfigurationError(
            f"JWT_SECRET_KEY must be set to a random string of at least {MIN_SECRET_LENGTH} characters in production "
            '(e.g. python -c "import secrets; print(secrets.token_urlsafe(48))")'
        )
