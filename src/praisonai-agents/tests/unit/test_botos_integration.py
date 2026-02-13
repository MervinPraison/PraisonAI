"""
Integration, smoke, and real-agent tests for BotOS architecture.

Covers:
- Bot with mock adapter lifecycle
- BotOS multi-bot orchestration
- Agent alone in Bot
- AgentTeam inside Bot/BotOS
- AgentFlow inside Bot/BotOS
- Platform extensibility
- from_config() YAML loader
- run() sync wrapper
- remove_bot()
- Custom platform registration + resolution
"""

import asyncio
import os
import tempfile
import pytest
from unittest.mock import MagicMock


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper: Mock adapter that simulates a platform bot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MockPlatformAdapter:
    """Simulates a platform bot adapter for testing."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.token = kwargs.get("token", "")
        self.agent = kwargs.get("agent")
        self.started = False
        self.stopped = False
        self.messages_sent = []

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    @property
    def is_running(self):
        return self.started and not self.stopped

    async def send_message(self, channel_id, content, **kwargs):
        self.messages_sent.append({"channel": channel_id, "content": content})
        return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Integration: Bot with mock adapter
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotWithMockAdapter:
    """Integration tests for Bot class with a mock platform adapter."""

    def setup_method(self):
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mockbot", MockPlatformAdapter)
        self._cleanup = lambda: _custom_platforms.pop("mockbot", None)

    def teardown_method(self):
        self._cleanup()

    @pytest.mark.asyncio
    async def test_bot_start_creates_adapter(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot", token="test-token")
        await bot.start()
        assert bot.adapter is not None
        assert isinstance(bot.adapter, MockPlatformAdapter)
        assert bot.adapter.started is True

    @pytest.mark.asyncio
    async def test_bot_stop(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot", token="test-token")
        await bot.start()
        await bot.stop()
        assert bot.adapter.stopped is True
        assert bot.is_running is False

    @pytest.mark.asyncio
    async def test_bot_passes_token_to_adapter(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot", token="my-secret-token")
        await bot.start()
        assert bot.adapter.token == "my-secret-token"

    @pytest.mark.asyncio
    async def test_bot_passes_agent_to_adapter(self):
        from praisonai.bots import Bot
        agent = MagicMock()
        agent.name = "test-agent"
        bot = Bot("mockbot", agent=agent, token="t")
        await bot.start()
        assert bot.adapter.agent is agent

    @pytest.mark.asyncio
    async def test_bot_send_message(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot", token="t")
        await bot.start()
        result = await bot.send_message("channel-1", "Hello!")
        assert result is True
        assert len(bot.adapter.messages_sent) == 1
        assert bot.adapter.messages_sent[0]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_bot_send_message_before_start_raises(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot", token="t")
        with pytest.raises(RuntimeError, match="not started"):
            await bot.send_message("ch", "msg")

    @pytest.mark.asyncio
    async def test_bot_passes_kwargs_to_adapter(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot", token="t", custom_param="hello")
        await bot.start()
        assert bot.adapter.kwargs.get("custom_param") == "hello"

    @pytest.mark.asyncio
    async def test_bot_repr(self):
        from praisonai.bots import Bot
        agent = MagicMock()
        agent.name = "myagent"
        bot = Bot("mockbot", agent=agent)
        assert "mockbot" in repr(bot)
        assert "myagent" in repr(bot)

    def test_bot_has_run_method(self):
        from praisonai.bots import Bot
        bot = Bot("mockbot")
        assert hasattr(bot, "run")
        assert callable(bot.run)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Integration: BotOS lifecycle
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotOSLifecycle:
    """Integration tests for BotOS multi-bot orchestration."""

    def setup_method(self):
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mock1", MockPlatformAdapter)
        register_platform("mock2", MockPlatformAdapter)
        self._cleanup = lambda: (_custom_platforms.pop("mock1", None), _custom_platforms.pop("mock2", None))

    def teardown_method(self):
        self._cleanup()

    @pytest.mark.asyncio
    async def test_botos_starts_all_bots(self):
        from praisonai.bots import BotOS, Bot
        bot1 = Bot("mock1", token="t1")
        bot2 = Bot("mock2", token="t2")
        botos = BotOS(bots=[bot1, bot2])

        # Start in background, stop quickly
        start_task = asyncio.create_task(botos.start())
        await asyncio.sleep(0.05)
        await botos.stop()
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

        assert bot1.adapter.started is True
        assert bot2.adapter.started is True

    def test_botos_remove_bot(self):
        from praisonai.bots import BotOS, Bot
        botos = BotOS(bots=[Bot("mock1"), Bot("mock2")])
        assert len(botos.list_bots()) == 2
        result = botos.remove_bot("mock1")
        assert result is True
        assert len(botos.list_bots()) == 1
        assert "mock2" in botos.list_bots()

    def test_botos_remove_bot_not_found(self):
        from praisonai.bots import BotOS
        botos = BotOS()
        assert botos.remove_bot("nonexistent") is False

    def test_botos_has_run_method(self):
        from praisonai.bots import BotOS
        botos = BotOS()
        assert hasattr(botos, "run")
        assert callable(botos.run)

    def test_botos_repr(self):
        from praisonai.bots import BotOS, Bot
        botos = BotOS(bots=[Bot("mock1"), Bot("mock2")])
        r = repr(botos)
        assert "mock1" in r
        assert "mock2" in r


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Real Agent in Bot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRealAgentInBot:
    """Tests with a real praisonaiagents.Agent inside Bot."""

    def setup_method(self):
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mockbot", MockPlatformAdapter)
        self._cleanup = lambda: _custom_platforms.pop("mockbot", None)

    def teardown_method(self):
        self._cleanup()

    def test_real_agent_in_bot(self):
        from praisonai.bots import Bot
        from praisonaiagents import Agent
        agent = Agent(name="helper", instructions="Be helpful")
        bot = Bot("mockbot", agent=agent, token="t")
        assert bot.agent is agent
        assert bot.agent.name == "helper"

    @pytest.mark.asyncio
    async def test_real_agent_passed_to_adapter(self):
        from praisonai.bots import Bot
        from praisonaiagents import Agent
        agent = Agent(name="helper", instructions="Be helpful")
        bot = Bot("mockbot", agent=agent, token="t")
        await bot.start()
        assert bot.adapter.agent is agent
        assert bot.adapter.agent.name == "helper"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. AgentTeam in Bot/BotOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAgentTeamInBotOS:
    """AgentTeam (multi-agent) inside Bot and BotOS."""

    def setup_method(self):
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mockbot", MockPlatformAdapter)
        self._cleanup = lambda: _custom_platforms.pop("mockbot", None)

    def teardown_method(self):
        self._cleanup()

    def test_agent_team_in_bot(self):
        from praisonai.bots import Bot
        from praisonaiagents import Agent, AgentTeam, Task
        researcher = Agent(name="researcher", instructions="Research topics")
        writer = Agent(name="writer", instructions="Write content")
        t1 = Task(name="research", description="Research AI", agent=researcher)
        t2 = Task(name="write", description="Write about AI", agent=writer)
        team = AgentTeam(agents=[researcher, writer], tasks=[t1, t2])

        bot = Bot("mockbot", agent=team, token="t")
        assert bot.agent is team

    @pytest.mark.asyncio
    async def test_agent_team_passed_to_adapter(self):
        from praisonai.bots import Bot
        from praisonaiagents import Agent, AgentTeam, Task
        a1 = Agent(name="a1", instructions="Do task 1")
        a2 = Agent(name="a2", instructions="Do task 2")
        t1 = Task(name="t1", description="Task 1", agent=a1)
        t2 = Task(name="t2", description="Task 2", agent=a2)
        team = AgentTeam(agents=[a1, a2], tasks=[t1, t2])

        bot = Bot("mockbot", agent=team, token="t")
        await bot.start()
        assert bot.adapter.agent is team

    def test_agent_team_in_botos(self):
        from praisonai.bots import BotOS, Bot
        from praisonaiagents import Agent, AgentTeam, Task
        a1 = Agent(name="a1", instructions="Task 1")
        a2 = Agent(name="a2", instructions="Task 2")
        t1 = Task(name="t1", description="T1", agent=a1)
        t2 = Task(name="t2", description="T2", agent=a2)
        team = AgentTeam(agents=[a1, a2], tasks=[t1, t2])

        botos = BotOS(bots=[Bot("mockbot", agent=team, token="t")])
        assert botos.get_bot("mockbot").agent is team


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. AgentFlow in Bot/BotOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAgentFlowInBotOS:
    """AgentFlow (deterministic workflow) inside Bot and BotOS."""

    def setup_method(self):
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mockbot", MockPlatformAdapter)
        self._cleanup = lambda: _custom_platforms.pop("mockbot", None)

    def teardown_method(self):
        self._cleanup()

    def test_agent_flow_in_bot(self):
        from praisonai.bots import Bot
        from praisonaiagents import Agent, AgentFlow, Task
        a1 = Agent(name="step1", instructions="Do step 1")
        a2 = Agent(name="step2", instructions="Do step 2")
        t1 = Task(name="t1", description="Step 1", agent=a1)
        t2 = Task(name="t2", description="Step 2", agent=a2)
        flow = AgentFlow(steps=[t1, t2])

        bot = Bot("mockbot", agent=flow, token="t")
        assert bot.agent is flow

    @pytest.mark.asyncio
    async def test_agent_flow_passed_to_adapter(self):
        from praisonai.bots import Bot
        from praisonaiagents import Agent, AgentFlow, Task
        a1 = Agent(name="s1", instructions="Step 1")
        a2 = Agent(name="s2", instructions="Step 2")
        t1 = Task(name="t1", description="S1", agent=a1)
        t2 = Task(name="t2", description="S2", agent=a2)
        flow = AgentFlow(steps=[t1, t2])

        bot = Bot("mockbot", agent=flow, token="t")
        await bot.start()
        assert bot.adapter.agent is flow

    def test_agent_flow_in_botos_multi_platform(self):
        """AgentFlow in BotOS across multiple platforms."""
        from praisonai.bots import BotOS, Bot
        from praisonaiagents import Agent, AgentFlow, Task
        a1 = Agent(name="s1", instructions="Step 1")
        t1 = Task(name="t1", description="S1", agent=a1)
        flow = AgentFlow(steps=[t1])

        botos = BotOS(bots=[
            Bot("mockbot", agent=flow, token="t1"),
        ])
        assert botos.get_bot("mockbot").agent is flow


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Platform Extensibility
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPlatformExtensibility:
    """Third-party platform registration and usage."""

    def teardown_method(self):
        from praisonai.bots._registry import _custom_platforms
        _custom_platforms.pop("custom_chat", None)
        _custom_platforms.pop("my_platform", None)

    def test_register_and_use_custom_platform(self):
        from praisonai.bots._registry import register_platform, resolve_adapter
        register_platform("custom_chat", MockPlatformAdapter)
        cls = resolve_adapter("custom_chat")
        assert cls is MockPlatformAdapter

    def test_custom_platform_in_list(self):
        from praisonai.bots._registry import register_platform, list_platforms
        register_platform("my_platform", MockPlatformAdapter)
        assert "my_platform" in list_platforms()

    @pytest.mark.asyncio
    async def test_custom_platform_in_bot(self):
        from praisonai.bots._registry import register_platform
        from praisonai.bots import Bot
        register_platform("custom_chat", MockPlatformAdapter)
        bot = Bot("custom_chat", token="tok")
        await bot.start()
        assert bot.adapter.started is True

    @pytest.mark.asyncio
    async def test_custom_platform_in_botos(self):
        from praisonai.bots._registry import register_platform
        from praisonai.bots import BotOS, Bot
        register_platform("custom_chat", MockPlatformAdapter)
        botos = BotOS(bots=[Bot("custom_chat", token="tok")])
        assert "custom_chat" in botos.list_bots()

    def test_resolve_unknown_platform_raises(self):
        from praisonai.bots._registry import resolve_adapter
        with pytest.raises(ValueError, match="Unknown platform"):
            resolve_adapter("nonexistent_xyz")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. from_config() YAML loader
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotOSFromConfig:
    """BotOS.from_config() YAML config loading."""

    def setup_method(self):
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mockbot", MockPlatformAdapter)
        self._cleanup = lambda: _custom_platforms.pop("mockbot", None)

    def teardown_method(self):
        self._cleanup()

    def test_from_config_basic(self):
        from praisonai.bots import BotOS
        yaml_content = """\
agent:
  name: test-bot
  instructions: Be helpful
platforms:
  mockbot:
    token: test-token-123
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            botos = BotOS.from_config(path)
            assert "mockbot" in botos.list_bots()
            bot = botos.get_bot("mockbot")
            assert bot.token == "test-token-123"
            assert bot.agent is not None
            assert bot.agent.name == "test-bot"
        finally:
            os.unlink(path)

    def test_from_config_env_var_resolution(self):
        from praisonai.bots import BotOS
        os.environ["TEST_BOTOS_TOKEN"] = "resolved-token"
        yaml_content = """\
agent:
  name: env-bot
  instructions: Be helpful
platforms:
  mockbot:
    token: ${TEST_BOTOS_TOKEN}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            botos = BotOS.from_config(path)
            bot = botos.get_bot("mockbot")
            assert bot.token == "resolved-token"
        finally:
            os.unlink(path)
            del os.environ["TEST_BOTOS_TOKEN"]

    def test_from_config_multi_platform(self):
        from praisonai.bots import BotOS
        from praisonai.bots._registry import register_platform, _custom_platforms
        register_platform("mock2", MockPlatformAdapter)

        yaml_content = """\
agent:
  name: multi-bot
  instructions: Handle multiple platforms
platforms:
  mockbot:
    token: tok1
  mock2:
    token: tok2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            botos = BotOS.from_config(path)
            assert len(botos.list_bots()) == 2
            assert "mockbot" in botos.list_bots()
            assert "mock2" in botos.list_bots()
        finally:
            os.unlink(path)
            _custom_platforms.pop("mock2", None)

    def test_from_config_invalid_raises(self):
        from praisonai.bots import BotOS
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid yaml content that is just a string")
            f.flush()
            path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid"):
                BotOS.from_config(path)
        finally:
            os.unlink(path)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Smoke Tests — import paths, hierarchy, class structure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSmoke:
    """Smoke tests for the BotOS architecture."""

    def test_all_import_paths(self):
        """All classes importable from expected paths."""
        from praisonaiagents.bots.protocols import BotOSProtocol
        from praisonaiagents.bots.config import BotOSConfig
        from praisonaiagents.bots import BotOSProtocol as P2
        from praisonaiagents.bots import BotOSConfig as C2
        from praisonaiagents import BotOSProtocol as P3
        from praisonaiagents import BotOSConfig as C3
        from praisonai.bots import Bot, BotOS
        from praisonai.bots._registry import (
            register_platform, list_platforms, resolve_adapter, get_platform_registry
        )
        assert all(x is not None for x in [
            BotOSProtocol, BotOSConfig, P2, C2, P3, C3,
            Bot, BotOS, register_platform, list_platforms,
            resolve_adapter, get_platform_registry
        ])

    def test_protocol_identity(self):
        """Same protocol from different paths."""
        from praisonaiagents.bots.protocols import BotOSProtocol as A
        from praisonaiagents import BotOSProtocol as B
        assert A is B

    def test_config_identity(self):
        from praisonaiagents.bots.config import BotOSConfig as A
        from praisonaiagents import BotOSConfig as B
        assert A is B

    def test_bot_class_hierarchy(self):
        """Bot hierarchy: BotOS > Bot > Agent."""
        from praisonai.bots import Bot, BotOS
        from praisonaiagents import Agent

        agent = Agent(name="test", instructions="test")
        bot = Bot("telegram", agent=agent)
        botos = BotOS(bots=[bot])

        assert botos.get_bot("telegram") is bot
        assert bot.agent is agent

    def test_builtin_platforms_count(self):
        from praisonai.bots._registry import list_platforms
        platforms = list_platforms()
        assert len(platforms) >= 4  # telegram, discord, slack, whatsapp

    def test_no_heavy_imports_on_bot_creation(self):
        """Creating Bot should NOT import platform libraries."""
        import sys
        from praisonai.bots import Bot
        Bot("telegram")
        assert "telegram" not in sys.modules
        assert "discord" not in sys.modules

    def test_no_heavy_imports_on_botos_creation(self):
        import sys
        from praisonai.bots import BotOS, Bot
        BotOS(bots=[Bot("telegram")])
        assert "telegram" not in sys.modules

    def test_botos_protocol_has_remove_bot(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert hasattr(BotOSProtocol, 'remove_bot')

    def test_bot_has_run_method(self):
        from praisonai.bots import Bot
        assert hasattr(Bot, 'run')

    def test_botos_has_run_method(self):
        from praisonai.bots import BotOS
        assert hasattr(BotOS, 'run')

    def test_botos_has_from_config(self):
        from praisonai.bots import BotOS
        assert hasattr(BotOS, 'from_config')
        assert callable(BotOS.from_config)
