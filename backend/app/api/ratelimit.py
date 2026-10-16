"""In-memory, per-client limits on failed sign-ins, wrong invite codes and feedback posts.

Clients are keyed by a salted hash of their IP held only in this process's memory; the IP is never logged or
stored. Behind the bundled Caddy proxy set TRUST_PROXY_HEADERS=true so the client IP comes from the last
X-Forwarded-For entry (the one Caddy wrote), not from the proxy's own address."""

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

_SALT = secrets.token_bytes(16)
_lock = threading.Lock()
_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

# bucket -> (max events, window seconds)
LIMITS = {
    "auth_fail": (10, 15 * 60),
    "invite_fail": (10, 15 * 60),
    "feedback": (30, 60 * 60),
}


def client_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            ip = fwd.split(",")[-1].strip()
    return hashlib.sha256(_SALT + ip.encode()).hexdigest()[:24]


def _prune(q: deque[float], window: float, now: float) -> None:
    while q and q[0] <= now - window:
        q.popleft()


def check(request: Request, bucket: str) -> None:
    """Raise 429 if this client is already over the bucket's limit."""
    limit, window = LIMITS[bucket]
    now = time.monotonic()
    with _lock:
        q = _events[(bucket, client_key(request))]
        _prune(q, window, now)
        if len(q) >= limit:
            retry = int(q[0] + window - now) + 1
            raise HTTPException(429, "too many attempts; try again later", {"Retry-After": str(retry)})


def record(request: Request, bucket: str) -> None:
    now = time.monotonic()
    with _lock:
        q = _events[(bucket, client_key(request))]
        _prune(q, LIMITS[bucket][1], now)
        q.append(now)


def hit(request: Request, bucket: str) -> None:
    """Check and count in one step (for actions limited whether or not they succeed)."""
    check(request, bucket)
    record(request, bucket)


def reset() -> None:
    with _lock:
        _events.clear()
