"""Fixtures for the local-resolver tests.

The autouse `no_sockets` fixture is the mechanism that proves offline safety: a
test that forgets to inject a transport fails loudly instead of silently hitting
whatever the developer happens to have running on :11434.
"""

import socket

import pytest

from praisonaiagents.local import HttpReply

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    """Any real socket construction in this directory is a test bug."""
    def _forbidden(self, *a, **kw):
        raise AssertionError(
            "tests/unit/llm/local must not open a socket; inject a transport"
        )
    monkeypatch.setattr(socket.socket, "__init__", _forbidden)


@pytest.fixture(autouse=True)
def clean_local_env(monkeypatch):
    for var in ("PRAISONAI_LOCAL_BASE_URL", "PRAISONAI_LOCAL_ENGINE",
                "PRAISONAI_LOCAL_MODEL", "PRAISONAI_LOCAL_TTL",
                "PRAISONAI_LOCAL_NEG_TTL", "PRAISONAI_LOCAL_TIMEOUT",
                "OLLAMA_HOST", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    from praisonaiagents.local import clear_cache
    clear_cache()
    yield
    clear_cache()


class Recorder:
    """A Transport that serves canned replies and records every call."""

    def __init__(self, routes, default=None):
        self.routes = routes
        self.default = default if default is not None else HttpReply(0, b"", "refused")
        self.calls = []

    def __call__(self, method, url, body, timeout):
        path = url.split("://", 1)[1].split("/", 1)
        path = "/" + (path[1] if len(path) > 1 else "")
        port = url.split(":")[2].split("/")[0] if url.count(":") >= 2 else ""
        self.calls.append((method, url))
        for key in ((method, port, path), (method, path)):
            if key in self.routes:
                return self.routes[key]
        return self.default

    def paths(self):
        return [u.split("://", 1)[1].split("/", 1)[-1] for _, u in self.calls]


@pytest.fixture
def transport():
    return Recorder


def ok(payload):
    import json
    return HttpReply(200, json.dumps(payload).encode())


def text(body, status=200):
    return HttpReply(status, body.encode())
