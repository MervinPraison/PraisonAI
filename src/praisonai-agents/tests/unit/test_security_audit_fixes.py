"""Smoke tests for security audit hardening."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


def test_workflow_include_skips_tools_without_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
    monkeypatch.delenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", raising=False)
    monkeypatch.chdir(tmp_path)

    child = tmp_path / "child_recipe"
    child.mkdir()
    marker = tmp_path / "marker.txt"
    (child / "tools.py").write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("x")\n')
    (child / "workflow.yaml").write_text("name: child\nsteps: []\n")

    from praisonaiagents.workflows.workflows import Workflow, include

    Workflow(steps=[include("child_recipe")]).run(input="", llm="dummy/local", stream=False)
    assert not marker.exists()


def test_web_crawl_rejects_redirect_to_loopback():
    pytest.importorskip("httpx")
    from praisonaiagents.tools.web_crawl_tools import _is_safe_crawl_url

    assert _is_safe_crawl_url("http://127.0.0.1/secret") is False
    assert _is_safe_crawl_url("http://example.com/") is True


def test_spider_blocks_rebound_hostname():
    from praisonaiagents.tools.spider_tools import _host_is_blocked

    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]):
        assert _host_is_blocked("rebound.example") is True


def test_file_memory_rejects_traversal_user_id():
    from praisonaiagents.memory.file_memory import FileMemory

    with pytest.raises(ValueError):
        FileMemory(user_id="../escape")


def test_ast_grep_rewrite_requires_approval():
    from praisonaiagents.tools import ast_grep_tool  # noqa: F401
    from praisonaiagents.approval import is_approval_required

    assert is_approval_required("ast_grep_rewrite") is True


def test_agent_server_enforces_auth_token():
    from praisonaiagents.server.server import AgentServer, ServerConfig

    server = AgentServer(config=ServerConfig(auth_token="secret-token"))
    request = type("Req", (), {"headers": {"Authorization": "Bearer wrong"}})()
    assert server._authorise_request(request) is False
    request_ok = type("Req", (), {"headers": {"Authorization": "Bearer secret-token"}})()
    assert server._authorise_request(request_ok) is True
