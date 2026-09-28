"""Operator commands.  Usage:
    python manage.py make-admin EMAIL
    python manage.py revoke-admin EMAIL
    python manage.py stats
"""
import sys

from app.db import connect, init_db


def main() -> None:
    init_db()
    conn = connect()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in ("make-admin", "revoke-admin") and len(sys.argv) == 3:
        n = conn.execute("UPDATE users SET is_admin = ? WHERE email = ?", (1 if cmd == "make-admin" else 0, sys.argv[2].lower())).rowcount
        print("updated" if n else "no such user")
    elif cmd == "stats":
        for t in ("users", "listings", "bookings", "reviews"):
            print(t, conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
