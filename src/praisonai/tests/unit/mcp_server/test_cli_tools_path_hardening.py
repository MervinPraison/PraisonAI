"""MCP CLI tools must not read arbitrary filesystem paths."""

from __future__ import annotations

import pytest


def test_resolve_cwd_yaml_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from praisonai.mcp_server.adapters import cli_tools

    (tmp_path / "workflow.yaml").write_text("framework: test\ntopic: t\n")

    path = cli_tools._resolve_cwd_yaml_path("workflow.yaml")
    assert path.name == "workflow.yaml"

    with pytest.raises(ValueError):
        cli_tools._resolve_cwd_yaml_path("../../etc/passwd")

    with pytest.raises(ValueError):
        cli_tools._resolve_cwd_yaml_path("/etc/passwd")
