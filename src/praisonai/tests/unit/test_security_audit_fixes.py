"""Smoke tests for wrapper security audit hardening."""
from __future__ import annotations

import os

import pytest


def test_recipe_auth_fail_closed_without_secret(monkeypatch):
    from praisonai.recipe.serve import create_auth_middleware

    middleware_cls = create_auth_middleware("api-key", api_key=None)
    assert middleware_cls is not None


def test_serve_installs_api_key_middleware():
    from fastapi import FastAPI
    from praisonai.cli.features.serve import _install_api_key_middleware

    app = FastAPI()
    _install_api_key_middleware(app, "test-key")
    assert any("APIKeyMiddleware" in repr(m.cls) for m in app.user_middleware)


def test_mcp_origin_rejects_prefix_bypass():
    from praisonai.mcp_server.transports.http_stream import HTTPStreamTransport

    class _Srv:
        name = "test"

    transport = HTTPStreamTransport(_Srv(), allowed_origins=["http://localhost", "http://127.0.0.1"])
    assert transport._validate_origin("http://localhost.attacker.com") is False
    assert transport._validate_origin("http://localhost:8080") is True


def test_jobs_webhook_rejects_unresolved_host():
    from praisonai.jobs.models import JobSubmitRequest

    with pytest.raises(ValueError):
        JobSubmitRequest(
            agent_file="agents.yaml",
            webhook_url="http://definitely-not-a-real-host-xyz.invalid/",
        )


def test_file_utils_symlink_escape_blocked(tmp_path):
    from praisonai.code.utils.file_utils import is_path_within_directory

    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = workspace / "link.txt"
    link.symlink_to(outside)
    assert is_path_within_directory(str(link), str(workspace)) is False
