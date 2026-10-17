from fastapi.testclient import TestClient

from app.config import get_settings


def test_a_forged_host_header_cannot_open_the_gate(monkeypatch):
    from app.api.main import app

    monkeypatch.setenv("DEMO_INVITE_CODE", "unit-test-invite")
    get_settings.cache_clear()
    try:
        c = TestClient(app)
        # request.url is rebuilt from Host, so this used to read as /api/health and pass the gate.
        assert c.get("/api/search?q=x", headers={"host": "x/api/health?"}).status_code == 401
        assert c.get("/api/search?q=x").status_code == 401
        assert c.get("/redoc").status_code == 404
    finally:
        get_settings.cache_clear()
