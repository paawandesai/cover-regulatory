"""HTTP Basic auth for the admin review endpoints, checked server-side on every request.

Run `uv run python -m app.api.auth` to create a password hash for ADMIN_PASSWORD_SCRYPT."""

import getpass
import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.api import ratelimit
from app.config import get_settings

_basic = HTTPBasic(auto_error=False)
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P)
    return hmac.compare_digest(digest.hex(), digest_hex)


_DUMMY_HASH = hash_password(secrets.token_hex(16))


def _any_reviewer() -> bool:
    from app.db.connection import connect

    with connect() as conn:
        return conn.execute("SELECT 1 FROM reviewer WHERE active LIMIT 1").fetchone() is not None


def _named_reviewer(username: str, password: str) -> str | None:
    from app.api.reviewers import find
    from app.db.connection import connect

    with connect() as conn:
        r = find(conn, username)
        if r is None:
            # Same scrypt cost as a real account, so timing doesn't reveal which usernames exist.
            verify_password(password, _DUMMY_HASH)
            return None
        if not verify_password(password, r["password_scrypt"]):
            return None
        conn.execute("UPDATE reviewer SET last_login_at = now() WHERE username = %s", (username,))
        conn.commit()
    return r["username"]


def require_admin(request: Request, credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)]) -> str:
    """A named reviewer account, or the bootstrap ADMIN_USERNAME account from the environment."""
    s = get_settings()
    if not (s.admin_username and s.admin_password_scrypt is not None) and not _any_reviewer():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin review is not configured")
    ratelimit.check(request, "auth_fail")
    who = None
    if credentials is not None:
        who = _named_reviewer(credentials.username, credentials.password)
        if (
            who is None
            and s.admin_username
            and s.admin_password_scrypt is not None
            and hmac.compare_digest(credentials.username.encode(), s.admin_username.encode())
            and verify_password(credentials.password, s.admin_password_scrypt.get_secret_value())
        ):
            who = s.admin_username
    if who is None:
        ratelimit.record(request, "auth_fail")
        # No "WWW-Authenticate: Basic": it would make browsers show their own sign-in prompt and cache what is typed
        # there, which the app's Sign out cannot clear.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return who


if __name__ == "__main__":
    pw = getpass.getpass("Admin password: ")
    if len(pw) < 12 or pw != getpass.getpass("Again: "):
        raise SystemExit("Passwords differ or are shorter than 12 characters.")
    print(hash_password(pw))
