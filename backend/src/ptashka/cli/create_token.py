"""Create a personal API token for an existing, active user, from the server shell.

    python -m ptashka.cli.create_token --email agent@example.com --name "Research agent" --scope write

Handy for agent accounts: no need to log in as the agent to mint its token.
The token is printed once; only its hash is stored.
"""

import argparse
import sys

from sqlalchemy import select

from ptashka.db.database import SessionLocal
from ptashka.models.db import TokenScope, User, UserStatus
from ptashka.services import token_service
from ptashka.services.auth_service import normalize_email


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--scope", choices=[s.value for s in TokenScope], default=TokenScope.READ.value)
    parser.add_argument("--expires-in-days", type=int, default=None)
    args = parser.parse_args(argv)

    # SessionLocal.begin(): this script is its own unit of work, committed when the block ends.
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == normalize_email(args.email)))
        if user is None or user.status != UserStatus.ACTIVE:
            print("No active user with that email", file=sys.stderr)
            return 1
        token, raw = token_service.create_token(db, user, args.name, TokenScope(args.scope), args.expires_in_days)
        print(f"Created {token.scope.value} token '{token.name}' for {user.email}:\n\n    {raw}\n\nIt won't be shown again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
