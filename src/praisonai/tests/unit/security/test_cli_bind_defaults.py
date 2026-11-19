"""Server CLIs and helpers outside the core SDK default to loopback.

Walks the Tier-2/3 package sources (``praisonai-code``, ``praisonai-browser``,
``praisonai-bot``, ``praisonai-mcp``, ``praisonai-sandbox``, the wrapper, …)
for an all-interfaces default on a host-like parameter, a ``typer.Option`` for
``--host`` or an argparse ``--host``. The core SDK has its own walk in
``praisonai-agents/tests/unit/security/test_bind_defaults.py``.

Explicit public binds (``--host 0.0.0.0``) stay supported; servers behind
these CLIs require a token for them.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[4]
ALL_INTERFACES = {"0.0.0.0", "::", "::0", ""}
PACKAGE_DIRS = sorted(
    p for p in SRC.glob("praisonai*/praisonai*")
    if p.is_dir()
    and p.name.replace("-", "_") == p.parent.name.replace("-", "_")
    and p.parent.name != "praisonai-agents"
)


def _hostish(name: str) -> bool:
    return "host" in name.lower()


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def _hits(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            pos = a.posonlyargs + a.args
            pairs = list(zip(pos[len(pos) - len(a.defaults):], a.defaults))
            pairs += [(x, d) for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
            for arg, default in pairs:
                # typer.Option("0.0.0.0", "--host") lands here as a Call default.
                if isinstance(default, ast.Call) and default.args:
                    value = _const(default.args[0])
                else:
                    value = _const(default)
                if _hostish(arg.arg) and value in ALL_INTERFACES:
                    yield f"{path}:{default.lineno} {arg.arg}"
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument":
            flags = [_const(x) for x in node.args]
            if any(isinstance(f, str) and "host" in f for f in flags):
                for kw in node.keywords:
                    if kw.arg == "default" and _const(kw.value) in ALL_INTERFACES:
                        yield f"{path}:{node.lineno} {flags}"


def test_package_dirs_found():
    names = {p.name for p in PACKAGE_DIRS}
    assert {"praisonai_code", "praisonai_browser", "praisonai"} <= names, names


def test_no_cli_or_server_defaults_to_all_interfaces():
    offenders = [h for d in PACKAGE_DIRS for py in sorted(d.rglob("*.py")) for h in _hits(py)]
    assert not offenders, "Default --host must be 127.0.0.1:\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "src, expected",
    [
        ("def f(host: str = typer.Option('0.0.0.0', '--host')): pass", 1),
        ("p.add_argument('--host', default='0.0.0.0')", 1),
        ("def f(bind_host='::'): pass", 1),
        ("def f(host=typer.Option('127.0.0.1', '--host')): pass", 0),
        ("p.add_argument('--port', default='0.0.0.0')", 0),
    ],
)
def test_walk_control(tmp_path, src, expected):
    f = tmp_path / "s.py"
    f.write_text(src + "\n")
    assert len(list(_hits(f))) == expected
