"""Named reviewer accounts and the audit log.

Each reviewer signs in with their own username and password, so every decision carries a person's name. The
ADMIN_USERNAME account from the environment remains as a bootstrap login. Accounts are managed on the server:

    python -m app.api.reviewers add <username> "<Display Name>"     (prompts for the password)
    python -m app.api.reviewers deactivate <username>
    python -m app.api.reviewers list
"""

import argparse
import getpass
import hashlib
import json

from app.db.connection import connect


def record(conn, actor: str, action: str, object_type: str, object_id, detail: dict | None = None) -> None:
    """Append one audit entry in the caller's transaction, so it commits with the change it records."""
    conn.execute(
        "INSERT INTO audit_log (actor, action, object_type, object_id, detail) VALUES (%s, %s, %s, %s, %s)",
        (actor, action, object_type, str(object_id), json.dumps(detail or {})),
    )


def token_ref(token: str) -> str:
    """Reports are logged by a hash of their link token: the log must not hand out working links."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def find(conn, username: str) -> dict | None:
    return conn.execute(
        "SELECT username, display_name, password_scrypt FROM reviewer WHERE username = %s AND active", (username,)
    ).fetchone()


def main() -> None:
    from app.api.auth import hash_password

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("username")
    a.add_argument("display_name")
    d = sub.add_parser("deactivate")
    d.add_argument("username")
    sub.add_parser("list")
    args = p.parse_args()
    with connect() as conn:
        if args.cmd == "add":
            pw = getpass.getpass("Password: ")
            if len(pw) < 12 or pw != getpass.getpass("Again: "):
                raise SystemExit("Passwords differ or are shorter than 12 characters.")
            conn.execute(
                """INSERT INTO reviewer (username, display_name, password_scrypt) VALUES (%s, %s, %s)
                   ON CONFLICT (username) DO UPDATE SET display_name = EXCLUDED.display_name,
                   password_scrypt = EXCLUDED.password_scrypt, active = true""",
                (args.username, args.display_name, hash_password(pw)),
            )
            record(conn, "server-cli", "reviewer_added", "reviewer", args.username)
        elif args.cmd == "deactivate":
            conn.execute("UPDATE reviewer SET active = false WHERE username = %s", (args.username,))
            record(conn, "server-cli", "reviewer_deactivated", "reviewer", args.username)
        else:
            for r in conn.execute("SELECT username, display_name, active, last_login_at FROM reviewer ORDER BY 1"):
                print(
                    r["username"],
                    "|",
                    r["display_name"],
                    "|",
                    "active" if r["active"] else "inactive",
                    "|",
                    r["last_login_at"],
                )
        conn.commit()


if __name__ == "__main__":
    main()
