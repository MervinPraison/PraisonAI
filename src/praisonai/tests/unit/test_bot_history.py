"""
TDD tests for bot session history injection.

Bot._apply_smart_defaults() should inject MemoryConfig(history=True)
so agents automatically get conversation context across turns.
"""

class TestBotHistoryInjection:
    """Tests for Bot._apply_smart_defaults() history wiring."""

    def _make_mock_agent(self, memory=None, name="test"):
        """Create a minimal mock Agent-like object with __name__ == 'Agent'."""

        class Agent:
            def __init__(self):
                self.name = name
                self.tools = []
                self.memory = memory
                self.chat_history = []
                self.llm = "gpt-4o-mini"
                self._approval_backend = None

            def chat(self, prompt):
                return f"echo: {prompt}"

        return Agent()

    def _make_bot(self, agent=None, platform="telegram", config=None):
        from praisonai.bots.bot import Bot
        return Bot(platform, agent=agent, config=config)

    def test_history_injected_when_no_memory(self):
        """Agent with no memory config gets history=True injected."""
        agent = self._make_mock_agent(memory=None)
        bot = self._make_bot(agent=agent)
        enhanced = bot._apply_smart_defaults(agent)
        # Should have memory config with history enabled
        mem = getattr(enhanced, "memory", None)
        assert mem is not None
        if isinstance(mem, dict):
            assert mem.get("history") is True

    def test_history_not_overridden_when_memory_set(self):
        """Agent with existing memory config is NOT overridden."""
        existing_memory = {"provider": "custom", "history": False}
        agent = self._make_mock_agent(memory=existing_memory)
        bot = self._make_bot(agent=agent)
        enhanced = bot._apply_smart_defaults(agent)
        # Should keep existing memory
        assert enhanced.memory == existing_memory

    def test_history_not_injected_for_team(self):
        """AgentTeam instances are NOT enhanced."""

        class MockTeam:
            pass

        team = MockTeam()
        bot = self._make_bot(agent=team)
        enhanced = bot._apply_smart_defaults(team)
        assert not hasattr(enhanced, "memory") or enhanced is team

    def test_none_agent_returns_none(self):
        """None agent passes through."""
        bot = self._make_bot(agent=None)
        assert bot._apply_smart_defaults(None) is None

    def test_no_session_id_in_injected_memory(self):
        """Injected memory has NO session_id — BotSessionManager isolates per-user."""
        agent = self._make_mock_agent(memory=None)
        bot = self._make_bot(agent=agent, platform="discord")
        enhanced = bot._apply_smart_defaults(agent)
        mem = getattr(enhanced, "memory", None)
        assert isinstance(mem, dict)
        assert "session_id" not in mem

    def test_memory_true_preserved(self):
        """Agent with memory=True is not overridden."""
        agent = self._make_mock_agent(memory=True)
        bot = self._make_bot(agent=agent)
        enhanced = bot._apply_smart_defaults(agent)
        # memory=True should be left alone
        assert enhanced.memory is True
