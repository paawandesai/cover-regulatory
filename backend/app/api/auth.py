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


def require_admin(request: Request, credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)]) -> str:
    s = get_settings()
    if not s.admin_username or s.admin_password_scrypt is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin review is not configured")
    ratelimit.check(request, "auth_fail")
    ok = (
        credentials is not None
        and hmac.compare_digest(credentials.username.encode(), s.admin_username.encode())
        and verify_password(credentials.password, s.admin_password_scrypt.get_secret_value())
    )
    if not ok:
        ratelimit.record(request, "auth_fail")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials", {"WWW-Authenticate": "Basic"})
    return s.admin_username


if __name__ == "__main__":
    pw = getpass.getpass("Admin password: ")
    if len(pw) < 12 or pw != getpass.getpass("Again: "):
        raise SystemExit("Passwords differ or are shorter than 12 characters.")
    print(hash_password(pw))
