"""Password hashing utilities using bcrypt."""

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt (the salt is stored inside the hash)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
