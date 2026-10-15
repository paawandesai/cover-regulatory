"""API tests against the local database. Skipped when it is not reachable."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.api.auth import hash_password
from app.config import get_settings

try:
    from app.db.connection import connect

    with connect() as _c:
        _c.execute("SELECT 1 FROM rule_fragment LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("database not reachable", allow_module_level=True)

from app.api.main import app

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "reviewer")
    monkeypatch.setenv("ADMIN_PASSWORD_SCRYPT", hash_password(PASSWORD))
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def auth(user="reviewer", pw=PASSWORD):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def test_health_has_no_secrets_and_noindex(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["X-Robots-Tag"].startswith("noindex")
    body = r.text
    assert "scrypt$" not in body and "sk-ant" not in body
    assert isinstance(r.json()["llm_key_configured"], bool)


def test_admin_requires_credentials(client):
    assert client.get("/api/admin/fragments").status_code == 401
    assert client.get("/api/admin/fragments", headers=auth(pw="wrong password")).status_code == 401
    assert client.get("/api/admin/fragments", headers=auth()).status_code == 200


def test_admin_disabled_without_config(monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_SCRYPT", raising=False)
    get_settings.cache_clear()
    try:
        r = TestClient(app).get("/api/admin/fragments", headers=auth())
        assert r.status_code == 503
    finally:
        get_settings.cache_clear()


def test_invalid_fragment_cannot_be_approved(client):
    with connect() as conn:
        row = conn.execute("SELECT id FROM rule_fragment WHERE status = 'invalid' LIMIT 1").fetchone()
    if row is None:
        pytest.skip("no invalid fragment to test with")
    r = client.post(f"/api/admin/fragments/{row['id']}", json={"decision": "approved"}, headers=auth())
    assert r.status_code == 409


def test_chunk_lookup(client):
    r = client.get("/api/chunks/does-not-exist")
    assert r.status_code == 404
