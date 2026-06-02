"""Regression tests for the MCP ``praisonai.rules.*`` tools.

Covers GHSA-9mqq-jqxf-grvw: an attacker-controlled ``rule_name`` such as
``../../../<site-packages>/x.pth`` would previously be joined directly
onto ``~/.praison/rules`` and the resulting file written, giving
arbitrary file write inside the user's home directory and persistent
RCE via Python ``.pth`` injection. After hardening, any traversal token,
directory separator, NUL byte, or leading dot in ``rule_name`` must be
rejected and the resolved path must remain inside the rules directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def rules_helpers(tmp_path, monkeypatch):
    """Register the rules tools against a sandboxed fake home dir."""
    monkeypatch.setenv("HOME", str(tmp_path))

    from praisonai.mcp_server.adapters import cli_tools as mod
    from praisonai.mcp_server.registry import get_tool_registry

    mod.register_cli_tools()
    reg = get_tool_registry()
    handlers = {
        name: reg.get(name).handler
        for name in (
            "praisonai.rules.create",
            "praisonai.rules.show",
            "praisonai.rules.delete",
            "praisonai.rules.list",
        )
    }
    return handlers, tmp_path


def test_create_rejects_path_traversal(rules_helpers):
    captured, tmp_path = rules_helpers
    rules_create = captured["praisonai.rules.create"]
    result = rules_create("../../evil.pth", "import os")
    assert "Error" in result or "invalid" in result.lower()
    # Marker file must NOT have escaped the rules directory.
    assert not (tmp_path / "evil.pth").exists()
    assert not (tmp_path.parent / "evil.pth").exists()


def test_create_rejects_absolute_separator(rules_helpers):
    captured, tmp_path = rules_helpers
    rules_create = captured["praisonai.rules.create"]
    for bad in ("/etc/passwd", "subdir/x", "..", ".", "\x00", ".bashrc"):
        result = rules_create(bad, "x")
        assert "Error" in result or "invalid" in result.lower(), bad


def test_create_allows_simple_filename(rules_helpers):
    captured, tmp_path = rules_helpers
    rules_create = captured["praisonai.rules.create"]
    out = rules_create("ok_rule.md", "hello")
    assert "Rule created" in out
    expected = Path(tmp_path) / ".praison" / "rules" / "ok_rule.md"
    assert expected.exists()
    assert expected.read_text() == "hello"


def test_show_and_delete_reject_traversal(rules_helpers):
    captured, tmp_path = rules_helpers
    rules_show = captured["praisonai.rules.show"]
    rules_delete = captured["praisonai.rules.delete"]
    for bad in ("../../etc/passwd", "subdir/x", "..", "/abs"):
        assert "Error" in rules_show(bad) or "invalid" in rules_show(bad).lower(), bad
        assert (
            "Error" in rules_delete(bad)
            or "invalid" in rules_delete(bad).lower()
        ), bad
