import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _no_demo_gate(monkeypatch):
    """Tests run without the hosted-demo invite gate, even where the environment sets one."""
    monkeypatch.delenv("DEMO_INVITE_CODE", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
