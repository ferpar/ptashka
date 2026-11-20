"""Create an active admin account, or promote an existing account to admin.

    python -m ptashka.cli.create_admin --email you@example.com --name "Fer"

The password is prompted for (or taken from PTASHKA_ADMIN_PASSWORD).
This is how the very first admin exists: nobody is around yet to approve them.
"""

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from ptashka.auth.password import hash_password
from ptashka.db.database import SessionLocal
from ptashka.models.db import User, UserRole, UserStatus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args(argv)

    try:
        # Same rules as registration, so the admin can actually log in.
        email = validate_email(args.email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as e:
        print(f"Invalid email: {e}", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            password = os.getenv("PTASHKA_ADMIN_PASSWORD") or getpass.getpass("Password: ")
            if not 8 <= len(password.encode()) <= 72:
                print("Password must be 8-72 bytes", file=sys.stderr)
                return 1
            user = User(email=email, hashed_password=hash_password(password), display_name=args.name)
            db.add(user)
            action = "Created"
        else:
            action = "Promoted"
        user.role = UserRole.ADMIN
        user.status = UserStatus.ACTIVE
        user.approved_at = user.approved_at or datetime.now(timezone.utc)
        db.commit()
        print(f"{action} admin {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
