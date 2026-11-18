"""Interactive account bootstrap without committed default credentials."""

import argparse
from getpass import getpass

from sqlalchemy import select

from app.auth import assign_role, hash_password, seed_roles
from app.database import SessionLocal
from app.models import User


def create_owner(email: str, name: str) -> None:
    """Create the initial owner after migrations have been applied."""
    password = getpass("Owner password (12+ characters): ")
    if len(password) < 12 or len(password) > 128:
        raise SystemExit("Password must contain 12 to 128 characters")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    with SessionLocal.begin() as db:
        seed_roles(db)
        if db.scalar(select(User).where(User.email == email.lower())):
            raise SystemExit("This email already exists")
        user = User(
            email=email.lower(),
            name=name,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
        assign_role(db, user.id, "owner")
    print("Owner created. Sign in through the administration dashboard.")


def main() -> None:
    """Parse the minimal operator interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create-owner"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Shop owner")
    args = parser.parse_args()
    create_owner(args.email, args.name)


if __name__ == "__main__":
    main()
