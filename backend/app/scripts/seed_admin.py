#!/usr/bin/env python3
"""Seeds (or updates) the initial platform_admin user (update44, argument
naming corrected in update47 — see below). Run once per environment —
idempotent, safe to re-run (updates the existing admin's password/name
rather than erroring on a duplicate).

platform_admin is deliberately NOT self-assignable through the public
/api/auth/signup endpoint (see app/schemas/auth.py's SELF_ASSIGNABLE_ROLES)
— this script is the only path to create one, matching the same
security-conscious pattern already used for the JWT keypair (generate_keys.py:
a privileged credential that must be provisioned deliberately, not through
a route anyone can hit).

update47: the admin identifier is a plain username (e.g. "Admin@GRMT"),
authenticated through the dedicated /api/auth/admin-login endpoint — never
through the EmailStr-validated /api/auth/login used by everyone else. The
User.email DB column is reused to store it (no schema change needed — it's
just a String(255) with no format constraint at the DB level), but calling
this script's argument --email was misleading given it doesn't need to be,
and will never be validated as, a real email address. --username is now the
primary flag; --email is kept as a backward-compatible alias for anyone who
already has update44/45/46-era commands saved.

Usage:
    python -m app.scripts.seed_admin
    python -m app.scripts.seed_admin --username "Admin@GRMT" --password "..." --full-name "..."
"""
import argparse
import sys

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.core import User

DEFAULT_USERNAME = "Admin@GRMT"
DEFAULT_PASSWORD = "24GRMT@2026"
DEFAULT_FULL_NAME = "GRMT Platform Administrator"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", "--email", dest="username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--full-name", default=DEFAULT_FULL_NAME)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)  # safe no-op if tables already exist — same as main.py's dev-mode call

    db = SessionLocal()
    try:
        # Case-insensitive match, matching how every other lookup in this
        # project treats the email/username column (see auth.py's signup:
        # User.email == payload.email.lower()).
        existing = db.query(User).filter(User.email == args.username.lower()).first()

        if existing is not None:
            existing.password_hash = hash_password(args.password)
            existing.full_name = args.full_name
            existing.role = "platform_admin"
            existing.is_active = True
            existing.is_email_verified = True
            db.commit()
            print(f"[ok] updated existing admin user: {args.username}")
        else:
            admin = User(
                email=args.username.lower(),
                password_hash=hash_password(args.password),
                full_name=args.full_name,
                role="platform_admin",
                is_active=True,
                is_email_verified=True,
            )
            db.add(admin)
            db.commit()
            print(f"[ok] created admin user: {args.username}")

        print("[ok] password is Argon2id-hashed in the database — never stored in plaintext, "
              "matching this project's existing password-handling for every other user")
        print("[ok] log in via /admin (NOT /login) with this exact username, "
              "authenticated through /api/auth/admin-login — the regular /api/auth/login "
              "endpoint validates its email field strictly and will reject this username.")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
