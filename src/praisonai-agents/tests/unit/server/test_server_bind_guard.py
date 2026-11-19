"""AgentServer defaults to loopback and refuses a keyless non-loopback bind."""

import inspect
from unittest.mock import patch

import pytest

from praisonaiagents.server.server import AgentServer, ServerConfig

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _start(server):
    # Never bind a socket: record what start() would serve instead.
    with patch.object(AgentServer, "_run_server") as run:
        server.start(blocking=True)
    return run


def test_default_host_is_loopback():
    assert inspect.signature(AgentServer.__init__).parameters["host"].default in LOOPBACK
    assert ServerConfig().host in LOOPBACK
    run = _start(AgentServer())
    run.assert_called_once()


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5"])
def test_public_bind_without_token_refuses(host):
    server = AgentServer(host=host)
    with patch.object(AgentServer, "_run_server") as run:
        with pytest.raises(ValueError, match="auth_token"):
            server.start(blocking=True)
    run.assert_not_called()
    assert server._running is False


def test_public_bind_with_token_starts():
    server = AgentServer(config=ServerConfig(host="0.0.0.0", auth_token="t0k"))
    run = _start(server)
    run.assert_called_once()
    assert server.host == "0.0.0.0"
