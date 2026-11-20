
"""Create or update the ZenTask Admin account securely."""

import os
import bcrypt
from database import create_tables, connect_db


def main():
    create_tables()

    name = os.getenv("ZENTASK_ADMIN_NAME")
    email = os.getenv("ZENTASK_ADMIN_EMAIL")
    password = os.getenv("ZENTASK_ADMIN_PASSWORD")

    if not all((name, email, password)):
        raise SystemExit(
            "Set ZENTASK_ADMIN_NAME, ZENTASK_ADMIN_EMAIL "
            "and ZENTASK_ADMIN_PASSWORD in .env"
        )

    if len(password) < 12:
        raise SystemExit("Admin password must be at least 12 characters.")

    c = connect_db()

    try:
        existing = c.execute(
            "SELECT user_id, role FROM users WHERE lower(email)=lower(?)",
            (email,)
        ).fetchone()

        hashed = bcrypt.hashpw(
            password.encode(),
            bcrypt.gensalt()
        ).decode()

        if existing:
            c.execute(
                """
                UPDATE users
                SET name=?, password=?, role='Admin', is_active=1
                WHERE user_id=?
                """,
                (name, hashed, existing["user_id"])
            )
            print("Existing account successfully converted to Admin.")

        else:
            c.execute(
                """
                INSERT INTO users
                (name, email, password, role, created_at, is_active)
                VALUES (?, ?, ?, 'Admin', datetime('now'), 1)
                """,
                (name, email.lower(), hashed)
            )
            print("New Admin account created successfully.")

        c.commit()
        print("Admin account is ready.")

    finally:
        c.close()


if __name__ == "__main__":
    main()
