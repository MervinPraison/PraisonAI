"""Every network server in every package binds through the shared guard.

Walks the source of each Python package in the monorepo for calls that open a
listening socket (uvicorn, aiohttp TCPSite, wsgiref/http.server, telegram
run_webhook, websockets.serve). Each one must either bind a loopback literal or
sit in a module that calls the shared bind guard
(``praisonaiagents.agent.launch_security.require_bind_token`` or a thin
wrapper of it). A new server that binds a caller-chosen host without the guard
fails here. Exemptions carry a reason.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[4]
PACKAGES = [
    "praisonai-agents/praisonaiagents",
    "praisonai/praisonai",
    "praisonai-code/praisonai_code",
    "praisonai-bot/praisonai_bot",
    "praisonai-mcp/praisonai_mcp",
    "praisonai-browser/praisonai_browser",
    "praisonai-sandbox/praisonai_sandbox",
    "praisonai-deploy/praisonai_deploy",
    "praisonai-train/praisonai_train",
]
SERVER_CALLS = {
    "uvicorn.run", "uvicorn.Config", "web.TCPSite", "make_server",
    "HTTPServer", "ThreadingHTTPServer", "run_webhook", "start_webhook", "websockets.serve",
}
GUARD_NAMES = ("require_bind_token", "resolve_launch_host", "webhook_bind_host", "guard_browser_app")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

EXEMPT = {
    "praisonai-agents/praisonaiagents/agent/server_registry.py":
        "binds for launch(); both callers run resolve_launch_host() first",
    "praisonai-bot/praisonai_bot/gateway/server.py":
        "gateway has its own auth mode (token required off loopback, resolve_auth_mode); V-H owns it",
}


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _matches(name):
    return any(name == c or name.endswith("." + c) for c in SERVER_CALLS)


def _binds_loopback_literal(call):
    candidates = list(call.args) + [k.value for k in call.keywords if k.arg in ("host", "listen")]
    for arg in candidates:
        if isinstance(arg, ast.Tuple) and arg.elts:
            arg = arg.elts[0]
        if isinstance(arg, ast.Constant) and arg.value in LOOPBACK:
            return True
    return False


def server_sites(path: Path):
    """(lineno, call name) for each socket-opening call not bound to a loopback literal."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name and _matches(name) and not _binds_loopback_literal(node):
                yield node.lineno, name


def _package_files():
    for pkg in PACKAGES:
        root = SRC / pkg
        if root.is_dir():
            yield from sorted(root.rglob("*.py"))


def test_every_server_uses_the_shared_bind_guard():
    unguarded = []
    for path in _package_files():
        rel = path.relative_to(SRC).as_posix()
        sites = list(server_sites(path))
        if not sites or rel in EXEMPT:
            continue
        if not any(g in path.read_text(encoding="utf-8") for g in GUARD_NAMES):
            unguarded += [f"{rel}:{line} {name}" for line, name in sites]
    assert not unguarded, (
        "These servers bind a caller-chosen host without the shared guard "
        "(praisonaiagents.agent.launch_security.require_bind_token):\n" + "\n".join(unguarded)
    )


def test_exemptions_are_still_servers():
    for rel in EXEMPT:
        path = SRC / rel
        if path.exists():
            assert list(server_sites(path)), f"{rel} no longer opens a socket; drop its exemption"


def test_walk_finds_the_shapes_it_must_catch(tmp_path):
    """Control: the walk flags caller-chosen binds and skips loopback literals."""
    sample = tmp_path / "s.py"
    sample.write_text(
        "import uvicorn\nfrom aiohttp import web\n"
        "uvicorn.run(app, host=host)\n"
        "web.TCPSite(runner, '0.0.0.0', 8080)\n"
        "HTTPServer((host, 0), H)\n"
        "self._application.run_webhook(listen='0.0.0.0')\n"
        "uvicorn.run(app, host='127.0.0.1')\n"
        "HTTPServer(('127.0.0.1', 0), H)\n"
    )
    assert [n for _, n in server_sites(sample)] == [
        "uvicorn.run", "web.TCPSite", "HTTPServer", "self._application.run_webhook"]


@pytest.mark.skipif(not (SRC / "praisonai/praisonai").is_dir(), reason="monorepo checkout only")
def test_walk_covers_every_package_present():
    present = [p for p in PACKAGES if (SRC / p).is_dir()]
    assert "praisonai-agents/praisonaiagents" in present
    assert sum(1 for _ in _package_files()) > 500
