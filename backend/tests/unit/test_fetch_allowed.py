"""Source downloads refuse the publisher sites, also when an allowed URL redirects to one."""

import httpx
import pytest

from app.ingest.regtext import ingest as I


def _client(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(I.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_a_redirect_to_a_publisher_site_is_refused(monkeypatch):
    def handler(req):
        if req.url.host == "planning.example.org":
            return httpx.Response(302, headers={"location": "https://codelibrary.amlegal.com/codes/los_angeles"})
        return httpx.Response(200, content=b"code text")

    _client(monkeypatch, handler)
    with pytest.raises(ValueError, match="amlegal"):
        I.fetch_allowed("https://planning.example.org/ordinance.pdf")


def test_an_allowed_source_is_fetched(monkeypatch):
    _client(monkeypatch, lambda req: httpx.Response(200, content=b"code text"))
    assert I.fetch_allowed("https://planning.example.org/ordinance.pdf").content == b"code text"
