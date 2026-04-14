"""Tests for auth protocols in core SDK."""

import asyncio
from typing import Any, Dict, Optional

from praisonaiagents.auth import (
    AuthIdentity,
    AuthBackendProtocol,
    WorkspaceContextProtocol,
    AuthConfig,
)
from praisonaiagents.auth.protocols import AuthIdentity as DirectAuthIdentity


# ── AuthIdentity tests ────────────────────────────────────────────────────────


class TestAuthIdentity:
    def test_create_user_identity(self):
        identity = AuthIdentity(id="u-1", type="user", email="a@b.com")
        assert identity.id == "u-1"
        assert identity.type == "user"
        assert identity.is_user is True
        assert identity.is_agent is False
        assert identity.email == "a@b.com"

    def test_create_agent_identity(self):
        identity = AuthIdentity(id="a-1", type="agent", name="CodeBot")
        assert identity.is_agent is True
        assert identity.is_user is False
        assert identity.name == "CodeBot"

    def test_roles(self):
        identity = AuthIdentity(id="u-1", roles=["owner", "admin"])
        assert identity.has_role("owner") is True
        assert identity.has_role("member") is False
        assert identity.has_any_role("member", "admin") is True
        assert identity.has_any_role("guest") is False

    def test_defaults(self):
        identity = AuthIdentity(id="u-1")
        assert identity.type == "user"
        assert identity.workspace_id is None
        assert identity.roles == []
        assert identity.email is None
        assert identity.name is None
        assert identity.metadata == {}

    def test_workspace_scoped(self):
        identity = AuthIdentity(
            id="u-1", workspace_id="ws-42", roles=["member"]
        )
        assert identity.workspace_id == "ws-42"
        assert identity.has_role("member") is True

    def test_metadata(self):
        identity = AuthIdentity(id="u-1", metadata={"plan": "pro"})
        assert identity.metadata["plan"] == "pro"

    def test_import_from_package(self):
        assert DirectAuthIdentity is AuthIdentity


# ── AuthConfig tests ──────────────────────────────────────────────────────────


class TestAuthConfig:
    def test_defaults(self):
        config = AuthConfig()
        assert config.backend is None
        assert config.token_ttl == 30 * 24 * 3600
        assert config.require_workspace is False

    def test_custom_config(self):
        config = AuthConfig(token_ttl=3600, require_workspace=True)
        assert config.token_ttl == 3600
        assert config.require_workspace is True


# ── AuthBackendProtocol tests ─────────────────────────────────────────────────


class MockAuthBackend:
    """Mock backend that satisfies AuthBackendProtocol via structural subtyping."""

    def __init__(self, user_db: Optional[Dict[str, AuthIdentity]] = None):
        self.user_db = user_db or {}

    async def authenticate(
        self, credentials: Dict[str, Any]
    ) -> Optional[AuthIdentity]:
        token = credentials.get("token", "")
        return self.user_db.get(token)

    async def authorize(
        self, identity: AuthIdentity, resource: str, action: str
    ) -> bool:
        if identity.has_role("owner"):
            return True
        if action == "read" and identity.has_role("member"):
            return True
        return False


class TestAuthBackendProtocol:
    def test_isinstance_check(self):
        backend = MockAuthBackend()
        assert isinstance(backend, AuthBackendProtocol)

    def test_authenticate_success(self):
        identity = AuthIdentity(id="u-1", type="user", roles=["owner"])
        backend = MockAuthBackend(user_db={"valid-token": identity})
        result = asyncio.run(backend.authenticate({"token": "valid-token"}))
        assert result is not None
        assert result.id == "u-1"

    def test_authenticate_failure(self):
        backend = MockAuthBackend()
        result = asyncio.run(backend.authenticate({"token": "bad-token"}))
        assert result is None

    def test_authorize_owner(self):
        identity = AuthIdentity(id="u-1", roles=["owner"])
        backend = MockAuthBackend()
        assert asyncio.run(backend.authorize(identity, "issue:1", "delete")) is True

    def test_authorize_member_read(self):
        identity = AuthIdentity(id="u-2", roles=["member"])
        backend = MockAuthBackend()
        assert asyncio.run(backend.authorize(identity, "issue:1", "read")) is True
        assert asyncio.run(backend.authorize(identity, "issue:1", "delete")) is False

    def test_authorize_no_roles(self):
        identity = AuthIdentity(id="u-3", roles=[])
        backend = MockAuthBackend()
        assert asyncio.run(backend.authorize(identity, "issue:1", "read")) is False


# ── WorkspaceContextProtocol tests ────────────────────────────────────────────


class MockWorkspaceContext:
    """Mock workspace context that satisfies WorkspaceContextProtocol."""

    def __init__(self):
        self.workspaces = {
            "ws-1": "You are an AI assistant for the Acme project.",
        }
        self.agents = {
            ("ws-1", "agent-1"): {
                "system_prompt": "You help with code reviews.",
                "model": "gpt-4o-mini",
                "tools": ["code_review"],
            },
        }

    async def get_workspace_context(self, workspace_id: str) -> Optional[str]:
        return self.workspaces.get(workspace_id)

    async def get_agent_config(
        self, workspace_id: str, agent_id: str
    ) -> Optional[Dict[str, Any]]:
        return self.agents.get((workspace_id, agent_id))


class TestWorkspaceContextProtocol:
    def test_isinstance_check(self):
        ctx = MockWorkspaceContext()
        assert isinstance(ctx, WorkspaceContextProtocol)

    def test_get_workspace_context(self):
        ctx = MockWorkspaceContext()
        result = asyncio.run(ctx.get_workspace_context("ws-1"))
        assert "Acme" in result

    def test_get_workspace_context_missing(self):
        ctx = MockWorkspaceContext()
        result = asyncio.run(ctx.get_workspace_context("ws-999"))
        assert result is None

    def test_get_agent_config(self):
        ctx = MockWorkspaceContext()
        result = asyncio.run(ctx.get_agent_config("ws-1", "agent-1"))
        assert result["model"] == "gpt-4o-mini"

    def test_get_agent_config_missing(self):
        ctx = MockWorkspaceContext()
        result = asyncio.run(ctx.get_agent_config("ws-1", "agent-999"))
        assert result is None


# ── Non-conforming class should fail isinstance ──────────────────────────────


class NotAnAuthBackend:
    def some_method(self):
        pass


class TestProtocolRejection:
    def test_non_conforming_class_fails(self):
        obj = NotAnAuthBackend()
        assert not isinstance(obj, AuthBackendProtocol)
        assert not isinstance(obj, WorkspaceContextProtocol)
