"""Per-client limits: failures are counted per bucket and per client, and the IP is only ever hashed."""

from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException

from app.api import ratelimit
from app.config import get_settings


def req(ip="203.0.113.5", fwd=None):
    return NS(client=NS(host=ip), headers={"x-forwarded-for": fwd} if fwd else {})


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    ratelimit.reset()
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    get_settings.cache_clear()
    yield
    ratelimit.reset()
    get_settings.cache_clear()


def test_blocks_after_the_limit_and_only_that_client():
    limit, _ = ratelimit.LIMITS["invite_fail"]
    for _ in range(limit):
        ratelimit.check(req(), "invite_fail")
        ratelimit.record(req(), "invite_fail")
    with pytest.raises(HTTPException) as e:
        ratelimit.check(req(), "invite_fail")
    assert e.value.status_code == 429 and int(e.value.headers["Retry-After"]) > 0
    ratelimit.check(req("198.51.100.7"), "invite_fail")  # another client is unaffected
    ratelimit.check(req(), "auth_fail")  # another bucket is unaffected


def test_forwarded_for_is_used_only_when_trusted(monkeypatch):
    a, b = req("10.0.0.2", "203.0.113.1"), req("10.0.0.2", "203.0.113.2")
    assert ratelimit.client_key(a) == ratelimit.client_key(b)  # untrusted: the proxy address is the client
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()
    assert ratelimit.client_key(a) != ratelimit.client_key(b)
    # The last entry is the one the proxy wrote; anything a client prepends is ignored.
    assert ratelimit.client_key(req("10.0.0.2", "1.2.3.4, 203.0.113.1")) == ratelimit.client_key(a)


def test_proxy_hops_pick_the_viewer_behind_cloudfront_and_the_alb(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    get_settings.cache_clear()
    viewer = ratelimit.client_key(req("10.0.1.9", "203.0.113.1, 130.176.0.1"))
    # A different CloudFront edge, and a forged entry the client prepended, change nothing.
    assert ratelimit.client_key(req("10.0.1.9", "1.2.3.4, 203.0.113.1, 130.176.0.2")) == viewer
    assert ratelimit.client_key(req("10.0.1.9", "203.0.113.2, 130.176.0.1")) != viewer
    # Fewer entries than hops: use the first rather than fail.
    assert ratelimit.client_key(req("10.0.1.9", "203.0.113.1")) == viewer


def test_key_is_a_hash_not_the_ip():
    assert "203.0.113.5" not in ratelimit.client_key(req())
