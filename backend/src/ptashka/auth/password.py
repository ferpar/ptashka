"""Password hashing utilities using bcrypt."""

import os

import bcrypt

# bcrypt's cost factor: each +1 doubles the work. 12 (~170 ms per hash) is the production setting;
# test suites set BCRYPT_ROUNDS=4 (~1 ms), because they create hundreds of throwaway users and the
# hashing, not the database, was ~90% of their run time. Still real bcrypt, just cheap.
# config.validate_settings refuses anything below 12 in production.
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt (the salt is stored inside the hash)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # The cost is read from the stored hash, so hashes made with another setting still verify.
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
