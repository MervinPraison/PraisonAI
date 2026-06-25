"""Tests for outstanding GHSA security fixes (round 3)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# GHSA-29w3 multiedit
def test_multiedit_rejects_path_outside_workspace(tmp_path):
    from praisonai.tools.multiedit import multiedit

    outside = tmp_path / "outside.txt"
    outside.write_text("hello")
    ws = tmp_path / "ws"
    ws.mkdir()
    result = multiedit(
        str(outside),
        [{"old": "hello", "new": "hi"}],
        workspace_root=str(ws),
    )
    assert result["success"] is False
    assert "outside workspace" in (result.get("error") or "").lower()


def test_multiedit_allows_file_inside_workspace(tmp_path):
    from praisonai.tools.multiedit import multiedit

    f = tmp_path / "file.txt"
    f.write_text("hello")
    result = multiedit(
        "file.txt",
        [{"old": "hello", "new": "hi"}],
        workspace_root=str(tmp_path),
    )
    assert result["success"] is True
    assert f.read_text() == "hi"


# GHSA-4pcv SSRF
def test_searxng_url_blocks_metadata_endpoint():
    from praisonaiagents.tools.url_safety import validate_searxng_url

    assert validate_searxng_url("http://169.254.169.254/latest/meta-data/") is None


def test_searxng_url_allows_localhost():
    from praisonaiagents.tools.url_safety import validate_searxng_url

    assert validate_searxng_url("http://localhost:32768/search") is not None


def test_searxng_search_blocks_ssrf():
    from praisonaiagents.tools.searxng_tools import searxng_search

    results = searxng_search("test", searxng_url="http://169.254.169.254/")
    assert results and "error" in results[0]


# GHSA-7qw2 recipe policy
def test_recipe_policy_detects_workflow_declared_dangerous_tools(tmp_path):
    from praisonai.recipe.core import _check_tool_policy
    from praisonai.recipe.models import RecipeConfig

    recipe_dir = tmp_path / "recipe"
    recipe_dir.mkdir()
    (recipe_dir / "workflow.yaml").write_text(
        "approve:\n  - execute_command\nagents:\n  helper:\n    tools:\n      - execute_command\n"
    )
    cfg = RecipeConfig(
        name="test",
        version="1.0.0",
        path=str(recipe_dir),
        raw={"workflow": "workflow.yaml"},
        requires={},
    )
    err = _check_tool_policy(cfg, {"allow_dangerous_tools": False})
    assert err is not None
    assert "execute_command" in err


# GHSA-jxcw A2U bind guard
def test_a2u_cmd_rejects_non_localhost_without_token(monkeypatch):
    from praisonai.cli.features.serve import ServeHandler

    monkeypatch.delenv("A2U_AUTH_TOKEN", raising=False)
    feature = ServeHandler()
    code = feature.cmd_a2u(["--host", "0.0.0.0", "--port", "9999"])
    assert code != 0


# GHSA-8ccj call auth
@pytest.mark.asyncio
async def test_call_auth_disabled_rejected_for_non_localhost_bind(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import HTTPException

    monkeypatch.delenv("CALL_SERVER_TOKEN", raising=False)
    monkeypatch.setenv("PRAISONAI_CALL_AUTH", "disabled")
    monkeypatch.setenv("PRAISONAI_CALL_BIND_HOST", "0.0.0.0")

    from praisonai.api import agent_invoke

    class _Req:
        query_params = {}

    with pytest.raises(HTTPException) as exc:
        await agent_invoke.verify_token(_Req(), authorization=None)
    assert "localhost" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_call_auth_disabled_rejects_spoofed_host_header(monkeypatch):
    """GHSA-2gpf: client Host header must not bypass bind check."""
    pytest.importorskip("fastapi")

    monkeypatch.delenv("CALL_SERVER_TOKEN", raising=False)
    monkeypatch.setenv("PRAISONAI_CALL_AUTH", "disabled")
    monkeypatch.setenv("PRAISONAI_CALL_BIND_HOST", "0.0.0.0")

    from fastapi import HTTPException
    from praisonai.api import agent_invoke

    class _Url:
        hostname = "127.0.0.1"

    class _Req:
        url = _Url()
        query_params = {}

    with pytest.raises(HTTPException):
        await agent_invoke.verify_token(_Req(), authorization=None)


@pytest.mark.asyncio
async def test_call_auth_disabled_allowed_on_localhost(monkeypatch):
    pytest.importorskip("fastapi")
    import warnings

    monkeypatch.delenv("CALL_SERVER_TOKEN", raising=False)
    monkeypatch.setenv("PRAISONAI_CALL_AUTH", "disabled")
    monkeypatch.setenv("PRAISONAI_CALL_BIND_HOST", "127.0.0.1")

    from praisonai.api import agent_invoke

    class _Req:
        query_params = {}

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        await agent_invoke.verify_token(_Req(), authorization=None)


# GHSA-g6j7 deploy codegen
def test_deploy_api_server_code_escapes_agents_file():
    from praisonai.deploy.api import generate_api_server_code

    malicious = 'agents.yaml"); import os; os.system("echo pwned'
    code = generate_api_server_code(malicious)
    assert f'agent_file="{malicious}"' not in code
    assert f"PraisonAI(agent_file={repr(malicious)})" in code
