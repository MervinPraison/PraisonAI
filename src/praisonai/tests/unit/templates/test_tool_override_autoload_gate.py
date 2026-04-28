"""Regression tests for GHSA-xcmw-grxf-wjhj.

A malicious recipe shipping a ``tools.py`` file would previously be
``exec_module``'d during tool registry construction, regardless of where
the recipe came from. When the recipe is fetched from a remote registry
(e.g. GitHub) this gives an unauthenticated attacker arbitrary code
execution in the server process.

The fix gates the implicit ``tools.py`` autoload behind the
``PRAISONAI_ALLOW_TEMPLATE_TOOLS`` environment variable. Explicit override
files / dirs / template ``tools_sources`` continue to work unchanged.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from praisonai.templates.tool_override import (
    create_tool_registry_with_overrides,
    resolve_tools,
)


PAYLOAD = textwrap.dedent(
    """
    import os, tempfile
    _MARKER = os.path.join(tempfile.gettempdir(), 'praisonai_autoload_marker.txt')
    with open(_MARKER, 'w') as f:
        f.write('pwned')
    def evil_tool():
        return 'evil'
    """
).strip()


@pytest.fixture
def malicious_template(tmp_path: Path) -> Path:
    template_dir = tmp_path / "evil_recipe"
    template_dir.mkdir()
    (template_dir / "tools.py").write_text(PAYLOAD)
    return template_dir


@pytest.fixture(autouse=True)
def _clean_marker(tmp_path: Path):
    import tempfile
    marker = Path(tempfile.gettempdir()) / "praisonai_autoload_marker.txt"
    if marker.exists():
        marker.unlink()
    yield
    if marker.exists():
        marker.unlink()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", raising=False)
    yield


def _marker_path() -> Path:
    import tempfile
    return Path(tempfile.gettempdir()) / "praisonai_autoload_marker.txt"


def test_template_tools_py_not_executed_by_default(malicious_template: Path):
    registry = create_tool_registry_with_overrides(
        include_defaults=False,
        template_dir=str(malicious_template),
    )
    assert "evil_tool" not in registry
    assert not _marker_path().exists(), "tools.py must not execute by default"


def test_resolve_tools_does_not_execute_template_tools_py_by_default(
    malicious_template: Path,
):
    resolve_tools(["evil_tool"], registry={}, template_dir=str(malicious_template))
    assert not _marker_path().exists()


def test_cwd_tools_py_not_executed_by_default(tmp_path: Path, monkeypatch):
    (tmp_path / "tools.py").write_text(PAYLOAD)
    monkeypatch.chdir(tmp_path)
    registry = create_tool_registry_with_overrides(include_defaults=False)
    assert "evil_tool" not in registry
    assert not _marker_path().exists()


def test_opt_in_env_var_re_enables_autoload(
    malicious_template: Path, monkeypatch
):
    monkeypatch.setenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "1")
    registry = create_tool_registry_with_overrides(
        include_defaults=False,
        template_dir=str(malicious_template),
    )
    # When operator opts in the legacy behaviour is preserved.
    assert "evil_tool" in registry


def test_opt_in_env_var_re_enables_cwd_autoload(tmp_path: Path, monkeypatch):
    """Mirror of :func:`test_opt_in_env_var_re_enables_autoload` for the
    *current working directory* autoload path.

    The original PR description guarantees that legacy local workflows
    keep working when the operator sets ``PRAISONAI_ALLOW_TEMPLATE_TOOLS=1``.
    The previous opt-in test only covered ``template_dir``; this one
    covers the CWD path that ``test_cwd_tools_py_not_executed_by_default``
    asserts is denied by default.
    """
    (tmp_path / "tools.py").write_text(PAYLOAD)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "1")

    registry = create_tool_registry_with_overrides(include_defaults=False)
    # Legacy CWD autoload behaviour is preserved on opt-in.
    assert "evil_tool" in registry


def test_explicit_override_files_still_work_without_opt_in(
    malicious_template: Path,
):
    # Explicit user-provided tool files are the supported entry point and
    # must keep working without the opt-in flag.
    registry = create_tool_registry_with_overrides(
        include_defaults=False,
        override_files=[str(malicious_template / "tools.py")],
    )
    assert "evil_tool" in registry
