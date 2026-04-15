"""Tests for PlatformWorkspaceContext (WorkspaceContextProtocol implementation)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from praisonai_platform.db.models import Workspace, Agent, _uuid, _utcnow
from praisonai_platform.services.workspace_context import PlatformWorkspaceContext


class TestWorkspaceContext:
    @pytest.mark.asyncio
    async def test_get_workspace_context_with_description(self, session: AsyncSession):
        ws = Workspace(
            id=_uuid(), name="TestWS", slug="test-ws",
            description="Build AI agents",
            created_at=_utcnow(),
        )
        session.add(ws)
        await session.commit()

        ctx = PlatformWorkspaceContext(session)
        result = await ctx.get_workspace_context(ws.id)
        assert result == "Build AI agents"

    @pytest.mark.asyncio
    async def test_get_workspace_context_with_settings(self, session: AsyncSession):
        ws = Workspace(
            id=_uuid(), name="TestWS2", slug="test-ws-2",
            description="Base context",
            settings={"agent_context": "Extended instructions"},
            created_at=_utcnow(),
        )
        session.add(ws)
        await session.commit()

        ctx = PlatformWorkspaceContext(session)
        result = await ctx.get_workspace_context(ws.id)
        assert "Base context" in result
        assert "Extended instructions" in result

    @pytest.mark.asyncio
    async def test_get_workspace_context_not_found(self, session: AsyncSession):
        ctx = PlatformWorkspaceContext(session)
        result = await ctx.get_workspace_context("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_workspace_context_empty(self, session: AsyncSession):
        ws = Workspace(
            id=_uuid(), name="EmptyWS", slug="empty-ws",
            created_at=_utcnow(),
        )
        session.add(ws)
        await session.commit()

        ctx = PlatformWorkspaceContext(session)
        result = await ctx.get_workspace_context(ws.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_agent_config(self, session: AsyncSession):
        ws_id = _uuid()
        ws = Workspace(id=ws_id, name="AgentWS", slug="agent-ws", created_at=_utcnow())
        agent = Agent(
            id=_uuid(), workspace_id=ws_id, name="CodeBot",
            instructions="You are a code assistant",
            runtime_mode="local",
            runtime_config={"model": "gpt-4", "tools": ["search"]},
            status="idle",
            max_concurrent_tasks=3,
            created_at=_utcnow(),
        )
        session.add_all([ws, agent])
        await session.commit()

        ctx = PlatformWorkspaceContext(session)
        config = await ctx.get_agent_config(ws_id, agent.id)

        assert config is not None
        assert config["name"] == "CodeBot"
        assert config["system_prompt"] == "You are a code assistant"
        assert config["max_concurrent_tasks"] == 3
        assert config["model"] == "gpt-4"
        assert config["tools"] == ["search"]
        assert config["runtime_mode"] == "local"

    @pytest.mark.asyncio
    async def test_get_agent_config_not_found(self, session: AsyncSession):
        ctx = PlatformWorkspaceContext(session)
        result = await ctx.get_agent_config("ws-1", "agent-nonexist")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_agent_config_wrong_workspace(self, session: AsyncSession):
        ws_id = _uuid()
        other_ws_id = _uuid()
        ws = Workspace(id=ws_id, name="WS1", slug="ws-1", created_at=_utcnow())
        ws2 = Workspace(id=other_ws_id, name="WS2", slug="ws-2", created_at=_utcnow())
        agent = Agent(
            id=_uuid(), workspace_id=ws_id, name="Bot",
            runtime_mode="local", status="idle",
            max_concurrent_tasks=1, created_at=_utcnow(),
        )
        session.add_all([ws, ws2, agent])
        await session.commit()

        ctx = PlatformWorkspaceContext(session)
        result = await ctx.get_agent_config(other_ws_id, agent.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_protocol_compliance(self, session: AsyncSession):
        """Verify PlatformWorkspaceContext satisfies WorkspaceContextProtocol."""
        from praisonaiagents.auth import WorkspaceContextProtocol
        ctx = PlatformWorkspaceContext(session)
        assert isinstance(ctx, WorkspaceContextProtocol)
