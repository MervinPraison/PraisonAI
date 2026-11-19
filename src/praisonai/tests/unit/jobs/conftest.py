import pytest


@pytest.fixture(autouse=True)
def _declared_loopback_bind(monkeypatch):
    """Jobs API tests run as start_server() does by default: a declared
    loopback bind and no API key (tests that need otherwise override it)."""
    monkeypatch.setenv("PRAISONAI_JOBS_BIND_HOST", "127.0.0.1")
    monkeypatch.delenv("PRAISONAI_JOBS_API_KEY", raising=False)
