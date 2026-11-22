"""Network servers default to loopback; a non-loopback bind is never keyless.

Covers the shared guard (``require_bind_token``), each SDK server that binds a
socket, and a source walk so a new server cannot reintroduce an all-interfaces
default.
"""

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

import praisonaiagents
from praisonaiagents.agent.launch_security import require_bind_token

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
ALL_INTERFACES = {"0.0.0.0", "::", "::0", ""}


@pytest.fixture(autouse=True)
def _no_ambient_tokens(monkeypatch):
    from praisonaiagents.agent import launch_security

    for var in (
        "MCP_SSE_AUTH_TOKEN", "MCP_AUTH_TOKEN", "MCP_SSE_ALLOWED_ORIGINS",
        "PRAISONAI_LAUNCH_AUTH_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(launch_security, "_GENERATED_TOKEN", None)


# ── shared guard ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("host", sorted(LOOPBACK))
def test_guard_allows_keyless_loopback(host):
    require_bind_token(host, None, server="s", hint="h")


@pytest.mark.parametrize("host", ["127.0.0.2", "0:0:0:0:0:0:0:1"])
def test_guard_treats_whole_loopback_range_as_loopback(host):
    require_bind_token(host, None, server="s", hint="h")


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.0.0.5", "example.com"])
def test_guard_refuses_keyless_non_loopback(host):
    with pytest.raises(ValueError, match="refuses to bind non-loopback host"):
        require_bind_token(host, None, server="s", hint="Set S_TOKEN")


def test_guard_allows_non_loopback_with_token():
    assert require_bind_token("0.0.0.0", "secret", server="s", hint="h") == "secret"


def test_guard_generate_mode_mints_exports_and_reuses_one_token(monkeypatch, capsys):
    monkeypatch.delenv("S_TOKEN", raising=False)
    first = require_bind_token("0.0.0.0", None, server="s", hint="h", generate_into="S_TOKEN")
    assert first and __import__("os").environ["S_TOKEN"] == first
    assert first in capsys.readouterr().out
    monkeypatch.delenv("S_TOKEN")
    assert require_bind_token("::", None, server="s", hint="h", generate_into="S_TOKEN") == first


def test_launch_guard_is_the_shared_guard():
    """resolve_launch_host delegates to require_bind_token (one policy)."""
    from praisonaiagents.agent import launch_security

    with patch.object(launch_security, "require_bind_token") as guard:
        launch_security.resolve_launch_host("0.0.0.0")
    guard.assert_called_once()


# ── A2A ──────────────────────────────────────────────────────────────────────

class _StubAgent:
    name = "stub"
    role = "stub"
    goal = "stub"
    backstory = ""
    tools = []
    chat_history = []

    def chat(self, text):
        return text


def _a2a(**kw):
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    from praisonaiagents.ui.a2a import A2A

    return A2A(agent=_StubAgent(), **kw)


def test_a2a_serve_default_host_is_loopback():
    a2a = _a2a()
    assert inspect.signature(type(a2a).serve).parameters["host"].default in LOOPBACK
    with patch("uvicorn.run") as run:
        a2a.serve()
    assert run.call_args.kwargs["host"] in LOOPBACK


def test_a2a_serve_public_bind_without_token_uses_shared_guard():
    from praisonaiagents.agent import launch_security

    a2a = _a2a()
    with patch("uvicorn.run"), patch.object(
        launch_security, "require_bind_token", wraps=launch_security.require_bind_token
    ) as guard:
        a2a.serve(host="0.0.0.0")
    guard.assert_called_once()
    assert a2a.auth_token


def test_a2a_serve_public_bind_with_token_starts():
    a2a = _a2a(auth_token="t0k")
    with patch("uvicorn.run") as run:
        a2a.serve(host="0.0.0.0", port=9999)
    assert run.call_args.kwargs["host"] == "0.0.0.0"


# ── MCP SSE ──────────────────────────────────────────────────────────────────

def _mcp_server():
    pytest.importorskip("mcp.server.sse")
    pytest.importorskip("uvicorn")
    from praisonaiagents.mcp.mcp_server import ToolsMCPServer

    def ping(text: str) -> str:
        """Echo."""
        return text

    return ToolsMCPServer(name="t", tools=[ping])


def test_mcp_sse_default_bind_is_loopback():
    server = _mcp_server()
    with patch("uvicorn.run") as run:
        server.run_sse()
    assert run.call_args.kwargs["host"] in LOOPBACK


def test_mcp_sse_public_bind_without_token_uses_shared_guard():
    from praisonaiagents.agent import launch_security

    server = _mcp_server()
    with patch("uvicorn.run"), patch.object(
        launch_security, "require_bind_token", wraps=launch_security.require_bind_token
    ) as guard:
        server.run_sse(host="0.0.0.0")
    guard.assert_called_once()
    assert __import__("os").environ["MCP_SSE_AUTH_TOKEN"]


def test_mcp_sse_public_bind_with_token_starts(monkeypatch):
    monkeypatch.setenv("MCP_SSE_AUTH_TOKEN", "t0k")
    server = _mcp_server()
    with patch("uvicorn.run") as run:
        server.run_sse(host="0.0.0.0")
    assert run.call_args.kwargs["host"] == "0.0.0.0"


# ── launch() plumbing defaults ───────────────────────────────────────────────

def test_launcher_protocol_and_registry_defaults_are_loopback():
    from praisonaiagents.agent.protocols import HttpLauncherProtocol, McpLauncherProtocol
    from praisonaiagents.agent.server_registry import _AgentServerRegistry

    for fn in (
        HttpLauncherProtocol.launch,
        McpLauncherProtocol.launch,
        _AgentServerRegistry.start_server_if_needed,
    ):
        assert inspect.signature(fn).parameters["host"].default in LOOPBACK, fn


# ── no new all-interfaces default anywhere in the package ────────────────────

def _is_host_name(name: str) -> bool:
    name = name.lower()
    return "host" in name or name in ("bind", "listen", "bind_address", "address")


def _all_interfaces_defaults(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        pairs = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            positional = args.posonlyargs + args.args
            pairs += zip(positional[len(positional) - len(args.defaults):], args.defaults)
            pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
            pairs = [(a.arg, d) for a, d in pairs]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            pairs = [(node.target.id, node.value)]
        for name, default in pairs:
            if (
                _is_host_name(name)
                and isinstance(default, ast.Constant)
                and default.value in ALL_INTERFACES
            ):
                yield f"{path}:{default.lineno} {name}={default.value!r}"


def test_no_server_defaults_to_all_interfaces():
    root = Path(praisonaiagents.__file__).parent
    offenders = [hit for py in sorted(root.rglob("*.py")) for hit in _all_interfaces_defaults(py)]
    assert not offenders, (
        "Network servers must default to 127.0.0.1 and use "
        "praisonaiagents.agent.launch_security.require_bind_token for "
        "non-loopback binds:\n" + "\n".join(offenders)
    )


def test_source_walk_detects_an_all_interfaces_default(tmp_path):
    """Control: the walk really flags the shapes it is meant to catch."""
    sample = tmp_path / "s.py"
    sample.write_text(
        "def serve(host: str = '0.0.0.0'): pass\n"
        "def run(*, bind_host='::'): pass\n"
        "class C:\n    host: str = '0.0.0.0'\n"
        "def ok(host='127.0.0.1', url_host='0.0.0.0x'): pass\n"
    )
    assert len(list(_all_interfaces_defaults(sample))) == 3


# ── constant-time token check shared by every server ─────────────────────────

def test_token_matches_semantics():
    from praisonaiagents.agent.launch_security import token_matches

    assert token_matches("sk-1", "sk-1")
    assert not token_matches("wrong", "sk-1")
    assert not token_matches(None, "sk-1") and not token_matches("", "sk-1")
    assert not token_matches("sk-1", None) and not token_matches(None, None)
    assert not token_matches("tökén", "sk-1")  # non-ASCII compared as bytes
    assert token_matches("tökén", "tökén")
