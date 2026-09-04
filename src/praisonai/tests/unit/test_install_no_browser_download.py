"""Regression guard for #4824: install must not force-download browsers.

`pip install praisonai` must have NO network side-effects. Previously
``setup.py`` overrode the install command with a ``PostInstallCommand`` that
ran ``playwright install`` (all engines), and the legacy ``build.py`` /
``post_install.py`` hooks did the same. That broke offline/air-gapped/CI
installs. These tests assert the install-time subprocess is gone and that
the packaging source contains no ``playwright install`` invocation.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

WRAPPER_PKG = Path(__file__).resolve().parents[2] / "praisonai"
SETUP_PY = WRAPPER_PKG / "setup.py"
POST_INSTALL = WRAPPER_PKG / "setup" / "post_install.py"
BUILD = WRAPPER_PKG / "setup" / "build.py"


def _calls(source: str):
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
    ]


def _code_only(source: str) -> str:
    """Return source with comments and string literals stripped.

    Guidance text (comments/docstrings that mention ``playwright install``)
    is intentionally allowed; only executable install-time side-effects are
    forbidden.
    """
    out: list[str] = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_setup_py_has_no_cmdclass_override():
    """setup.py must call plain setup() with no install-command override."""
    code = _code_only(SETUP_PY.read_text())
    assert "PostInstallCommand" not in code
    assert "cmdclass" not in code


def test_setup_py_does_not_invoke_playwright():
    code = _code_only(SETUP_PY.read_text())
    assert "playwright" not in code
    assert "subprocess" not in code


def test_post_install_main_is_noop():
    """post_install.main() must not spawn processes or download browsers."""
    source = POST_INSTALL.read_text()
    assert "subprocess" not in _code_only(source)
    for call in _calls(source):
        func = call.func
        name = getattr(func, "attr", getattr(func, "id", ""))
        assert name not in {"run", "call", "check_call", "Popen", "system"}, (
            f"post_install.py must not invoke {name}(...)"
        )


def test_build_hook_is_passthrough():
    """build.build(setup_kwargs) must be a pure pass-through shim."""
    source = BUILD.read_text()
    code = _code_only(source)
    assert "subprocess" not in code
    assert "playwright" not in code

    ns: dict = {}
    exec(compile(ast.parse(source), str(BUILD), "exec"), ns)  # noqa: S102
    sentinel = {"marker": object()}
    assert ns["build"](sentinel) is sentinel
